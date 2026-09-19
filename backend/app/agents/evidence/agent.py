"""The Evidence Agent

Neutral evidence analysis for the court. Two tasks:

- ``analyze`` (EVIDENCE_ANALYSIS) - before the debate, assess the important
  claims, every evidence item, contradictions, every witness, and missing
  evidence. Provenance is traced from the record in code and attached.
- ``review`` (EVIDENCE_REVIEW) - after the parties argue, check whether each
  argument's citations actually support its claim.

Both run through the shared validated-generation loop: output that cites
anything outside the record, or whose statuses contradict its own
citations, is rejected and regenerated.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from app.domain import Argument, Case, CourtMessage, CourtStage, JudgeQuestion, MessageType
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
    SYSTEM_PROMPT,
    build_analysis_prompt,
    build_correction_prompt,
    build_review_prompt,
)
from .provenance import ProvenanceRecord, trace_case_provenance
from .schema import (
    ArgumentSupport,
    ClaimStatus,
    EvidenceAnalysisOutput,
    EvidenceReviewOutput,
)
from .validation import EvidenceAnalysisValidator, EvidenceFlag, EvidenceReviewValidator

EVIDENCE_AGENT_ID = "evidence_agent"


class EvidenceAgentError(AgentError):
    """The Evidence Agent could not produce valid output"""


class EvidenceAnalysis(BaseModel):
    """Accepted EVIDENCE_ANALYSIS result"""

    output: EvidenceAnalysisOutput
    provenance: List[ProvenanceRecord]
    message: CourtMessage
    flags: List[EvidenceFlag] = Field(default_factory=list)
    attempts: List[AgentAttempt] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    provider: str = ""
    model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)

    def claims_with_status(self, status: ClaimStatus) -> List[str]:
        """Claim texts with a given status"""
        return [c.claim for c in self.output.claims if c.status == status]

    @property
    def rejected_attempts(self) -> int:
        return sum(1 for a in self.attempts if not a.accepted)


class EvidenceReview(BaseModel):
    """Accepted EVIDENCE_REVIEW result"""

    output: EvidenceReviewOutput
    message: CourtMessage
    flags: List[EvidenceFlag] = Field(default_factory=list)
    attempts: List[AgentAttempt] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    provider: str = ""
    model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)

    @property
    def unsupported_argument_ids(self) -> List[str]:
        return [
            r.argument_id
            for r in self.output.reviews
            if r.support == ArgumentSupport.UNSUPPORTED
        ]

    @property
    def rejected_attempts(self) -> int:
        return sum(1 for a in self.attempts if not a.accepted)


class EvidenceAgent:
    """Neutral evidence analyst"""

    agent_id = EVIDENCE_AGENT_ID

    def __init__(
        self,
        provider: LLMProvider,
        registry: Optional[LegalRuleRegistry] = None,
        log: Optional[InteractionLog] = None,
        max_attempts: int = 3,
        max_tokens: int = 16000,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.provider = provider
        self.registry = registry or LegalRuleRegistry()
        self.log = log if log is not None else InteractionLog()
        self.max_attempts = max_attempts
        self.max_tokens = max_tokens
        self.analysis_schema = strict_json_schema(EvidenceAnalysisOutput)
        self.review_schema = strict_json_schema(EvidenceReviewOutput)

    # ------------------------------------------------------------------
    # EVIDENCE_ANALYSIS
    # ------------------------------------------------------------------

    def build_analysis_request(self, case: Case, evaluation: CaseEvaluation) -> LLMRequest:
        return LLMRequest(
            system=SYSTEM_PROMPT,
            messages=[
                LLMMessage(
                    role=MessageRole.USER,
                    content=build_analysis_prompt(case, evaluation, self.registry),
                )
            ],
            json_schema=self.analysis_schema,
            schema_name="evidence_analysis",
            max_tokens=self.max_tokens,
        )

    def analyze(self, case: Case, evaluation: CaseEvaluation) -> EvidenceAnalysis:
        """Neutral analysis of the record before the debate"""
        validator = EvidenceAnalysisValidator(case, evaluation, self.registry)

        def parse(
            text: str,
        ) -> Tuple[Optional[Tuple[EvidenceAnalysisOutput, List[EvidenceFlag]]], List[str]]:
            output, errors = parse_model_output(text, EvidenceAnalysisOutput)
            if output is None:
                return None, errors
            report = validator.validate(output)
            return (output, report.flags), report.errors

        generation = generate_validated(
            provider=self.provider,
            log=self.log,
            agent_id=self.agent_id,
            prompt_version=PROMPT_VERSION,
            case_id=case.case_id,
            request=self.build_analysis_request(case, evaluation),
            parse=parse,
            max_attempts=self.max_attempts,
            correction=build_correction_prompt,
            error_cls=EvidenceAgentError,
            task="evidence analysis",
        )
        output, flags = generation.output
        counts = {
            status.value: sum(1 for c in output.claims if c.status == status)
            for status in ClaimStatus
        }
        message = CourtMessage(
            message_id="MSG-EVIDENCE-ANALYSIS",
            case_id=case.case_id,
            sender=self.agent_id,
            recipient="court",
            message_type=MessageType.EVIDENCE_ANALYSIS,
            stage=CourtStage.EVIDENCE_ANALYSIS,
            claim=output.summary,
            evidence_ids=[e.evidence_id for e in output.evidence],
            reasoning=(
                f"{len(output.claims)} claims ({counts['established']} established, "
                f"{counts['disputed']} disputed, {counts['unsupported']} unsupported); "
                f"{len(output.contradictions)} contradictions; "
                f"{len(output.missing_evidence)} missing-evidence items."
            ),
        )
        return EvidenceAnalysis(
            output=output,
            provenance=trace_case_provenance(case),
            message=message,
            flags=flags,
            attempts=generation.attempts,
            provider=generation.response.provider,
            model=generation.response.model,
            usage=generation.usage,
        )

    # ------------------------------------------------------------------
    # EVIDENCE_REVIEW
    # ------------------------------------------------------------------

    def build_review_request(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        arguments: Sequence[Argument],
        under_review: Sequence[Argument],
        evidence_context: Optional[Dict[str, Any]] = None,
        judge_questions: Sequence[JudgeQuestion] = (),
    ) -> LLMRequest:
        return LLMRequest(
            system=SYSTEM_PROMPT,
            messages=[
                LLMMessage(
                    role=MessageRole.USER,
                    content=build_review_prompt(
                        case,
                        evaluation,
                        self.registry,
                        arguments,
                        under_review,
                        evidence_context,
                        judge_questions,
                    ),
                )
            ],
            json_schema=self.review_schema,
            schema_name="evidence_review",
            max_tokens=self.max_tokens,
        )

    def review(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        arguments: Sequence[Argument],
        under_review: Optional[Sequence[Argument]] = None,
        message_id: str = "MSG-EVIDENCE-REVIEW",
        evidence_context: Optional[Dict[str, Any]] = None,
        judge_questions: Sequence[JudgeQuestion] = (),
    ) -> EvidenceReview:
        """Check whether arguments' citations support their claims

        ``arguments`` is every argument presented (context); ``under_review``
        is the subset to review, defaulting to all of them. ``evidence_context``
        carries the agent's earlier analysis so reviews stay consistent with it.
        """
        targets = list(under_review) if under_review is not None else list(arguments)
        if not targets:
            raise ValueError("There are no arguments to review")
        validator = EvidenceReviewValidator(targets)

        def parse(
            text: str,
        ) -> Tuple[Optional[Tuple[EvidenceReviewOutput, List[EvidenceFlag]]], List[str]]:
            output, errors = parse_model_output(text, EvidenceReviewOutput)
            if output is None:
                return None, errors
            report = validator.validate(output)
            return (output, report.flags), report.errors

        generation = generate_validated(
            provider=self.provider,
            log=self.log,
            agent_id=self.agent_id,
            prompt_version=PROMPT_VERSION,
            case_id=case.case_id,
            request=self.build_review_request(
                case, evaluation, arguments, targets, evidence_context, judge_questions
            ),
            parse=parse,
            max_attempts=self.max_attempts,
            correction=build_correction_prompt,
            error_cls=EvidenceAgentError,
            task="evidence review",
        )
        output, flags = generation.output
        tally = {
            s.value: sum(1 for r in output.reviews if r.support == s) for s in ArgumentSupport
        }
        message = CourtMessage(
            message_id=message_id,
            case_id=case.case_id,
            sender=self.agent_id,
            recipient="court",
            message_type=MessageType.EVIDENCE_REVIEW,
            stage=CourtStage.EVIDENCE_REVIEW,
            claim=output.summary,
            argument_ids=[r.argument_id for r in output.reviews],
            reasoning=(
                f"{tally['supported']} supported, {tally['partially_supported']} partially "
                f"supported, {tally['unsupported']} unsupported."
            ),
        )
        return EvidenceReview(
            output=output,
            message=message,
            flags=flags,
            attempts=generation.attempts,
            provider=generation.response.provider,
            model=generation.response.model,
            usage=generation.usage,
        )


def evidence_context(
    analysis: Optional[EvidenceAnalysis],
    reviews: Sequence[EvidenceReview] = (),
) -> Optional[Dict[str, Any]]:
    """The Evidence Agent's work as plain data for the shared case record

    Returns None when the agent has not run, so the record carries no
    ``evidence_analysis`` section at all.
    """
    if analysis is None and not reviews:
        return None
    context: Dict[str, Any] = {}
    if analysis is not None:
        context.update(analysis.output.model_dump(mode="json"))
        context["provenance"] = [p.model_dump() for p in analysis.provenance]
    context["argument_reviews"] = [
        r.model_dump(mode="json") for review in reviews for r in review.output.reviews
    ]
    return context
