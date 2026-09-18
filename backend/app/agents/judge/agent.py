"""The Judge Agent

Case -> Judge Agent -> Decision.

The agent asks the model for a structured decision, then parses and validates
it. Output that cites anything outside the record, or that is structurally
incomplete, is rejected: the violation is logged, the model is told exactly
what was wrong, and it is asked to regenerate. After ``max_attempts``
rejections the agent fails loudly - it never returns an unvalidated decision.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from app.domain import Argument, Case, Verdict
from app.llm import (
    InteractionLog,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    MessageRole,
    TokenUsage,
    strict_json_schema,
)
from app.rules import CaseEvaluation, LegalRuleRegistry

from ..base import AgentAttempt, AgentError, generate_validated, parse_model_output
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_correction_prompt, build_user_prompt
from .schema import JudgeDecisionOutput
from .validation import EngineDivergence, JudgeOutputValidator

DISCLAIMER = (
    "Research simulation only. This system does not provide legal advice or determine "
    "real legal rights or obligations."
)


# Kept as a name for callers written against Phase 3.
JudgeAttempt = AgentAttempt


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


class JudgeAgentError(AgentError):
    """The judge could not produce a valid decision"""


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
        evidence_context: Optional[Dict[str, Any]] = None,
        jury_context: Optional[Dict[str, Any]] = None,
    ) -> LLMRequest:
        """The initial request for a case (also useful to inspect the prompt)"""
        return LLMRequest(
            system=SYSTEM_PROMPT,
            messages=[
                LLMMessage(
                    role=MessageRole.USER,
                    content=build_user_prompt(
                        case, evaluation, self.registry, arguments, evidence_context, jury_context
                    ),
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
        evidence_context: Optional[Dict[str, Any]] = None,
        jury_context: Optional[Dict[str, Any]] = None,
    ) -> JudgeResult:
        """Decide every charge, regenerating until the output validates"""
        validator = JudgeOutputValidator(
            case,
            evaluation,
            registry=self.registry,
            arguments=arguments,
            strict_engine_alignment=self.strict_engine_alignment,
        )
        request = self.build_request(
            case, evaluation, arguments, evidence_context, jury_context
        )

        def parse(
            text: str,
        ) -> Tuple[Optional[Tuple[JudgeDecisionOutput, List[EngineDivergence]]], List[str]]:
            output, errors = parse_model_output(text, JudgeDecisionOutput)
            if output is None:
                return None, errors
            report = validator.validate(output)
            return (output, report.divergences), report.messages

        generation = generate_validated(
            provider=self.provider,
            log=self.log,
            agent_id=self.agent_id,
            prompt_version=PROMPT_VERSION,
            case_id=case.case_id,
            request=request,
            parse=parse,
            max_attempts=self.max_attempts,
            correction=build_correction_prompt,
            error_cls=JudgeAgentError,
            task="decision",
        )
        output, divergences = generation.output
        response = generation.response
        return JudgeResult(
            verdict=self._to_verdict(
                case, output, divergences, len(generation.attempts), response.model
            ),
            decision=output,
            divergences=divergences,
            attempts=generation.attempts,
            provider=response.provider,
            model=response.model,
            usage=generation.usage,
        )

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

