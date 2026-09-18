"""The Judge Agent

Case -> Judge Agent -> Decision.

The agent asks the model for a structured decision, then parses and validates
it. Output that cites anything outside the record, or that is structurally
incomplete, is rejected: the violation is logged, the model is told exactly
what was wrong, and it is asked to regenerate. After ``max_attempts``
rejections the agent fails loudly - it never returns an unvalidated decision.
"""

import json
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from app.domain import Argument, Case, Verdict
from app.llm import (
    InteractionLog,
    LLMError,
    LLMMessage,
    LLMOutputError,
    LLMProvider,
    LLMRequest,
    MessageRole,
    TokenUsage,
    strict_json_schema,
)
from app.rules import CaseEvaluation, LegalRuleRegistry

from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_correction_prompt, build_user_prompt
from .schema import JudgeDecisionOutput
from .validation import EngineDivergence, JudgeOutputValidator

DISCLAIMER = (
    "Research simulation only. This system does not provide legal advice or determine "
    "real legal rights or obligations."
)


class JudgeAttempt(BaseModel):
    """One generation attempt and why it was accepted or rejected"""

    attempt: int
    accepted: bool
    errors: List[str] = Field(default_factory=list)
    output: str = ""


class JudgeResult(BaseModel):
    """A validated judicial decision and how it was reached"""

    verdict: Verdict
    decision: JudgeDecisionOutput
    divergences: List[EngineDivergence] = Field(default_factory=list)
    attempts: List[JudgeAttempt] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    provider: str = ""
    model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)

    @property
    def rejected_attempts(self) -> int:
        return sum(1 for a in self.attempts if not a.accepted)


class JudgeAgentError(Exception):
    """The judge could not produce a valid decision"""

    def __init__(self, message: str, attempts: Optional[List[JudgeAttempt]] = None) -> None:
        super().__init__(message)
        self.attempts = attempts or []


class JudgeAgent:
    """Produces a reasoned, validated decision for every charge in a case"""

    agent_id = "judge_agent"

    def __init__(
        self,
        provider: LLMProvider,
        registry: Optional[LegalRuleRegistry] = None,
        log: Optional[InteractionLog] = None,
        max_attempts: int = 3,
        max_tokens: int = 16000,
        strict_engine_alignment: bool = False,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.provider = provider
        self.registry = registry or LegalRuleRegistry()
        self.log = log if log is not None else InteractionLog()
        self.max_attempts = max_attempts
        self.max_tokens = max_tokens
        self.strict_engine_alignment = strict_engine_alignment
        self.output_schema = strict_json_schema(JudgeDecisionOutput)

    def build_request(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        arguments: Sequence[Argument] = (),
    ) -> LLMRequest:
        """The initial request for a case (also useful to inspect the prompt)"""
        return LLMRequest(
            system=SYSTEM_PROMPT,
            messages=[
                LLMMessage(
                    role=MessageRole.USER,
                    content=build_user_prompt(case, evaluation, self.registry, arguments),
                )
            ],
            json_schema=self.output_schema,
            schema_name="judge_decision",
            max_tokens=self.max_tokens,
        )

    def decide(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        arguments: Sequence[Argument] = (),
    ) -> JudgeResult:
        """Decide every charge, regenerating until the output validates"""
        validator = JudgeOutputValidator(
            case,
            evaluation,
            registry=self.registry,
            arguments=arguments,
            strict_engine_alignment=self.strict_engine_alignment,
        )
        request = self.build_request(case, evaluation, arguments)
        attempts: List[JudgeAttempt] = []
        usage = TokenUsage()

        for number in range(1, self.max_attempts + 1):
            try:
                response = self.provider.generate(request)
            except LLMError as exc:
                self.log.record(
                    agent_id=self.agent_id,
                    prompt_version=PROMPT_VERSION,
                    request=request,
                    case_id=case.case_id,
                    attempt=number,
                    error=f"{type(exc).__name__}: {exc}",
                )
                attempts.append(JudgeAttempt(attempt=number, accepted=False, errors=[str(exc)]))
                raise JudgeAgentError(
                    f"Model call failed on attempt {number}: {exc}", attempts
                ) from exc

            usage = _add_usage(usage, response.usage)
            output, errors, divergences = self._parse_and_validate(response.text, validator)

            self.log.record(
                agent_id=self.agent_id,
                prompt_version=PROMPT_VERSION,
                request=request,
                response=response,
                case_id=case.case_id,
                attempt=number,
                validation_passed=not errors,
                validation_errors=errors,
            )
            attempts.append(
                JudgeAttempt(
                    attempt=number, accepted=not errors, errors=errors, output=response.text
                )
            )

            if output is not None and not errors:
                return JudgeResult(
                    verdict=self._to_verdict(case, output, divergences, number, response.model),
                    decision=output,
                    divergences=divergences,
                    attempts=attempts,
                    provider=response.provider,
                    model=response.model,
                    usage=usage,
                )

            # Rejected: show the model its own output and exactly what was wrong.
            request = request.model_copy(
                update={
                    "messages": request.messages
                    + [
                        LLMMessage(role=MessageRole.ASSISTANT, content=response.text),
                        LLMMessage(role=MessageRole.USER, content=build_correction_prompt(errors)),
                    ]
                }
            )

        raise JudgeAgentError(
            f"No valid decision after {self.max_attempts} attempt(s); "
            f"last errors: {'; '.join(attempts[-1].errors)}",
            attempts,
        )

    @staticmethod
    def _parse_and_validate(
        text: str, validator: JudgeOutputValidator
    ) -> Tuple[Optional[JudgeDecisionOutput], List[str], List[EngineDivergence]]:
        """Parse model text; return (output, rejection reasons, divergences)"""
        try:
            output = JudgeDecisionOutput.model_validate(json.loads(text))
        except json.JSONDecodeError as exc:
            return None, [str(LLMOutputError(f"Output is not valid JSON: {exc}"))], []
        except PydanticValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            return None, [f"Output does not match the required schema: {problems}"], []

        report = validator.validate(output)
        return output, report.messages, report.divergences

    def _to_verdict(
        self,
        case: Case,
        output: JudgeDecisionOutput,
        divergences: List[EngineDivergence],
        attempts: int,
        model: str,
    ) -> Verdict:
        """Map the structured decision onto the domain Verdict"""
        charge_lines = [
            f"{c.charge} ({c.rule_id}): {c.reasoning}" for c in output.charge_decisions
        ]
        return Verdict(
            verdict_id=f"V_{case.case_id}_JUDGE",
            case_id=case.case_id,
            agent_id=self.agent_id,
            charges=list(case.charges),
            decision="; ".join(
                f"{c.charge}: {c.decision.value}" for c in output.charge_decisions
            ),
            reasoning="\n\n".join([output.analysis] + charge_lines),
            evidence_used=output.referenced_evidence_ids(),
            laws_used=output.referenced_rule_ids(),
            unresolved_questions=list(output.unresolved_questions),
            confidence=output.overall_confidence,
            metadata={
                "charge_decisions": [c.model_dump(mode="json") for c in output.charge_decisions],
                "prompt_version": PROMPT_VERSION,
                "provider": self.provider.name,
                "model": model,
                "attempts": attempts,
                "engine_divergences": [d.model_dump() for d in divergences],
                "disclaimer": DISCLAIMER,
            },
        )


def _add_usage(total: TokenUsage, extra: TokenUsage) -> TokenUsage:
    return TokenUsage(
        input_tokens=total.input_tokens + extra.input_tokens,
        output_tokens=total.output_tokens + extra.output_tokens,
        cache_read_input_tokens=total.cache_read_input_tokens + extra.cache_read_input_tokens,
    )
