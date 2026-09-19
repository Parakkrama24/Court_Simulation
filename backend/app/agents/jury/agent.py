"""Jury agents

Each juror decides independently first (JURY_INDEPENDENT_DELIBERATION), then
optionally reconsiders once with the whole panel's independent decisions in
view (JURY_DELIBERATION). Both rounds run through the shared
validated-generation loop and produce a domain ``Verdict`` and a structured
``CourtMessage``.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple, Type

from pydantic import BaseModel, Field

from app.domain import (
    Argument,
    Case,
    CourtMessage,
    CourtStage,
    JudgeQuestion,
    MessageType,
    Verdict,
)
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
from .prompts import (
    PROMPT_VERSION,
    build_correction_prompt,
    build_deliberation_prompt,
    build_independent_prompt,
    build_system_prompt,
)
from .schema import JurorDeliberationOutput, JurorVerdictOutput
from .validation import JurorOutputValidator


class JurorAgentError(AgentError):
    """A juror could not produce a valid verdict"""


class JurorDecision(BaseModel):
    """One juror's accepted decision in one round"""

    juror_id: str
    stage: CourtStage
    output: JurorVerdictOutput
    verdict: Verdict
    message: CourtMessage
    changed_charges: List[str] = Field(
        default_factory=list, description="Charges whose verdict changed in deliberation"
    )
    attempts: List[AgentAttempt] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    provider: str = ""
    model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)

    @property
    def rejected_attempts(self) -> int:
        return sum(1 for a in self.attempts if not a.accepted)


class JurorAgent:
    """One member of the jury"""

    def __init__(
        self,
        juror_id: str,
        provider: LLMProvider,
        registry: Optional[LegalRuleRegistry] = None,
        log: Optional[InteractionLog] = None,
        max_attempts: int = 3,
        max_tokens: int = 16000,
        perspective: Optional[str] = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.juror_id = juror_id
        self.provider = provider
        self.registry = registry or LegalRuleRegistry()
        self.log = log if log is not None else InteractionLog()
        self.max_attempts = max_attempts
        self.max_tokens = max_tokens
        self.perspective = perspective
        self.system_prompt = build_system_prompt(juror_id, perspective)

    @property
    def agent_id(self) -> str:
        return self.juror_id

    def _request(
        self, content: str, schema: Type[BaseModel], schema_name: str
    ) -> LLMRequest:
        return LLMRequest(
            system=self.system_prompt,
            messages=[LLMMessage(role=MessageRole.USER, content=content)],
            json_schema=strict_json_schema(schema),
            schema_name=schema_name,
            max_tokens=self.max_tokens,
        )

    # ------------------------------------------------------------------
    # JURY_INDEPENDENT_DELIBERATION
    # ------------------------------------------------------------------

    def build_independent_request(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        arguments: Sequence[Argument] = (),
        evidence_context: Optional[Dict[str, Any]] = None,
        judge_questions: Sequence[JudgeQuestion] = (),
    ) -> LLMRequest:
        """The independent-round request: built from the record alone"""
        return self._request(
            build_independent_prompt(
                case, evaluation, self.registry, arguments, evidence_context, judge_questions
            ),
            JurorVerdictOutput,
            "juror_verdict",
        )

    def decide_independently(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        arguments: Sequence[Argument] = (),
        evidence_context: Optional[Dict[str, Any]] = None,
        judge_questions: Sequence[JudgeQuestion] = (),
    ) -> JurorDecision:
        """Decide every charge without any view of the other jurors"""
        return self._run(
            case,
            self.build_independent_request(
                case, evaluation, arguments, evidence_context, judge_questions
            ),
            JurorVerdictOutput,
            JurorOutputValidator(case, arguments, self.registry),
            CourtStage.JURY_INDEPENDENT_DELIBERATION,
            previous=None,
        )

    # ------------------------------------------------------------------
    # JURY_DELIBERATION
    # ------------------------------------------------------------------

    def build_deliberation_request(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        arguments: Sequence[Argument],
        evidence_context: Optional[Dict[str, Any]],
        panel: Dict[str, JurorVerdictOutput],
        judge_questions: Sequence[JudgeQuestion] = (),
    ) -> LLMRequest:
        return self._request(
            build_deliberation_prompt(
                case,
                evaluation,
                self.registry,
                arguments,
                evidence_context,
                self.juror_id,
                panel,
                judge_questions,
            ),
            JurorDeliberationOutput,
            "juror_deliberation",
        )

    def deliberate(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        arguments: Sequence[Argument],
        evidence_context: Optional[Dict[str, Any]],
        panel: Dict[str, JurorVerdictOutput],
        judge_questions: Sequence[JudgeQuestion] = (),
    ) -> JurorDecision:
        """Reconsider once, with every juror's independent decision in view"""
        if self.juror_id not in panel:
            raise ValueError(f"{self.juror_id} has no independent decision in the panel")
        previous = panel[self.juror_id]
        return self._run(
            case,
            self.build_deliberation_request(
                case, evaluation, arguments, evidence_context, panel, judge_questions
            ),
            JurorDeliberationOutput,
            JurorOutputValidator(case, arguments, self.registry, previous=previous),
            CourtStage.JURY_DELIBERATION,
            previous=previous,
        )

    # ------------------------------------------------------------------

    def _run(
        self,
        case: Case,
        request: LLMRequest,
        schema: Type[JurorVerdictOutput],
        validator: JurorOutputValidator,
        stage: CourtStage,
        previous: Optional[JurorVerdictOutput],
    ) -> JurorDecision:
        def parse(text: str) -> Tuple[Optional[JurorVerdictOutput], List[str]]:
            output, errors = parse_model_output(text, schema)
            if output is None:
                return None, errors
            return output, validator.validate(output).errors

        generation = generate_validated(
            provider=self.provider,
            log=self.log,
            agent_id=self.juror_id,
            prompt_version=PROMPT_VERSION,
            case_id=case.case_id,
            request=request,
            parse=parse,
            max_attempts=self.max_attempts,
            correction=build_correction_prompt,
            error_cls=JurorAgentError,
            task=f"verdict from {self.juror_id} at {stage.value}",
        )
        output = generation.output

        changed: List[str] = []
        if previous is not None:
            before = {v.charge: v.verdict for v in previous.charge_verdicts}
            changed = [
                v.charge
                for v in output.charge_verdicts
                if v.charge in before and before[v.charge] != v.verdict
            ]

        round_code = "IND" if stage == CourtStage.JURY_INDEPENDENT_DELIBERATION else "DELIB"
        verdict = self._to_verdict(case, output, round_code)
        message = CourtMessage(
            message_id=f"MSG-{self.juror_id.upper()}-{round_code}",
            case_id=case.case_id,
            sender=self.juror_id,
            recipient="court",
            message_type=MessageType.JURY_VERDICT,
            stage=stage,
            claim=verdict.decision,
            argument_ids=list(output.arguments_considered),
            evidence_ids=list(verdict.evidence_used),
            law_ids=list(verdict.laws_used),
            reasoning=output.reasoning,
            metadata={"changed_charges": changed} if previous is not None else {},
        )
        return JurorDecision(
            juror_id=self.juror_id,
            stage=stage,
            output=output,
            verdict=verdict,
            message=message,
            changed_charges=changed,
            attempts=generation.attempts,
            provider=generation.response.provider,
            model=generation.response.model,
            usage=generation.usage,
        )

    def _to_verdict(self, case: Case, output: JurorVerdictOutput, round_code: str) -> Verdict:
        """Map a juror's decision onto the domain Verdict"""
        evidence = list(
            dict.fromkeys(eid for v in output.charge_verdicts for eid in v.evidence_ids)
        )
        laws = list(dict.fromkeys(rid for v in output.charge_verdicts for rid in v.rule_ids))
        return Verdict(
            verdict_id=f"V_{case.case_id}_{self.juror_id.upper()}_{round_code}",
            case_id=case.case_id,
            agent_id=self.juror_id,
            charges=list(case.charges),
            decision="; ".join(f"{v.charge}: {v.verdict.value}" for v in output.charge_verdicts),
            reasoning=output.reasoning,
            evidence_used=evidence,
            laws_used=laws,
            unresolved_questions=list(output.uncertainties),
            confidence=output.confidence,
            metadata={
                "charge_verdicts": [v.model_dump(mode="json") for v in output.charge_verdicts],
                "arguments_considered": list(output.arguments_considered),
                "prompt_version": PROMPT_VERSION,
                "perspective": self.perspective,
            },
        )
