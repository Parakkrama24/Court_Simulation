"""The Prosecution and Defense agents

One class serves both sides; the role decides the objective, the stage
decides the task. Each turn is generated, validated against the record and
the debate so far, and regenerated on rejection - then converted into domain
``Argument`` objects with court-assigned IDs and a structured ``CourtMessage``.
"""

from typing import Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from app.domain import Argument, Case, CourtMessage, CourtStage
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
from .prompts import PROMPT_VERSION, build_correction_prompt, build_system_prompt, build_user_prompt
from .roles import STAGE_CODES, STAGE_MESSAGE_TYPES, STAGE_SPEAKERS, AdvocateRole
from .schema import AdvocateTurnOutput
from .validation import AdvocacyFlag, AdvocateTurnValidator

JUDGE_AGENT_ID = "judge_agent"


class AdvocateAgentError(AgentError):
    """An advocate could not produce a valid turn"""


class AdvocateTurn(BaseModel):
    """One accepted turn in court"""

    stage: CourtStage
    role: AdvocateRole
    agent_id: str
    statement: str
    arguments: List[Argument]
    message: CourtMessage
    flags: List[AdvocacyFlag] = Field(default_factory=list)
    attempts: List[AgentAttempt] = Field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    provider: str = ""
    model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)

    @property
    def rejected_attempts(self) -> int:
        return sum(1 for a in self.attempts if not a.accepted)


class AdvocateAgent:
    """Prosecution or defense counsel"""

    def __init__(
        self,
        role: AdvocateRole,
        provider: LLMProvider,
        registry: Optional[LegalRuleRegistry] = None,
        log: Optional[InteractionLog] = None,
        max_attempts: int = 3,
        max_tokens: int = 16000,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.role = role
        self.provider = provider
        self.registry = registry or LegalRuleRegistry()
        self.log = log if log is not None else InteractionLog()
        self.max_attempts = max_attempts
        self.max_tokens = max_tokens
        self.output_schema = strict_json_schema(AdvocateTurnOutput)

    @property
    def agent_id(self) -> str:
        return self.role.agent_id

    def _check_stage(self, stage: CourtStage) -> None:
        if self.role not in STAGE_SPEAKERS.get(stage, []):
            raise ValueError(f"The {self.role.value} does not speak at {stage.value}")

    def build_request(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        stage: CourtStage,
        prior_arguments: Sequence[Argument] = (),
    ) -> LLMRequest:
        """The initial request for one turn (also useful to inspect the prompt)"""
        self._check_stage(stage)
        return LLMRequest(
            system=build_system_prompt(self.role),
            messages=[
                LLMMessage(
                    role=MessageRole.USER,
                    content=build_user_prompt(
                        case, evaluation, self.registry, self.role, stage, prior_arguments
                    ),
                )
            ],
            json_schema=self.output_schema,
            schema_name="advocate_turn",
            max_tokens=self.max_tokens,
        )

    def argue(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        stage: CourtStage,
        prior_arguments: Sequence[Argument] = (),
        id_prefix: Optional[str] = None,
    ) -> AdvocateTurn:
        """Produce one validated turn at ``stage``"""
        request = self.build_request(case, evaluation, stage, prior_arguments)
        validator = AdvocateTurnValidator(
            case, self.role, stage, prior_arguments, registry=self.registry
        )

        def parse(
            text: str,
        ) -> Tuple[Optional[Tuple[AdvocateTurnOutput, List[AdvocacyFlag]]], List[str]]:
            output, errors = parse_model_output(text, AdvocateTurnOutput)
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
            request=request,
            parse=parse,
            max_attempts=self.max_attempts,
            correction=build_correction_prompt,
            error_cls=AdvocateAgentError,
            task=f"{self.role.value} turn at {stage.value}",
        )
        output, flags = generation.output
        prefix = id_prefix or f"{self.role.code}-{STAGE_CODES[stage]}"
        arguments = self._to_arguments(output, stage, prefix)

        return AdvocateTurn(
            stage=stage,
            role=self.role,
            agent_id=self.agent_id,
            statement=output.statement,
            arguments=arguments,
            message=self._to_message(case, stage, output, arguments, prefix),
            flags=flags,
            attempts=generation.attempts,
            provider=generation.response.provider,
            model=generation.response.model,
            usage=generation.usage,
        )

    def _to_arguments(
        self, output: AdvocateTurnOutput, stage: CourtStage, prefix: str
    ) -> List[Argument]:
        """Assign court IDs and map drafts onto the domain Argument"""
        arguments = []
        for index, draft in enumerate(output.arguments, start=1):
            element_rules = [e.rule_id for e in draft.elements]
            arguments.append(
                Argument(
                    argument_id=f"{prefix}-{index}",
                    agent_id=self.agent_id,
                    claim=draft.claim,
                    evidence_ids=list(draft.evidence_ids),
                    fact_ids=list(draft.fact_ids),
                    witness_ids=list(draft.witness_ids),
                    law_ids=list(dict.fromkeys(draft.law_ids + element_rules)),
                    counter_argument_ids=list(draft.responds_to),
                    reasoning=draft.reasoning,
                    confidence=draft.confidence,
                    metadata={
                        "stage": stage.value,
                        "charges": list(draft.charges),
                        "elements": [e.model_dump() for e in draft.elements],
                        "assumptions": list(draft.assumptions),
                        "prompt_version": PROMPT_VERSION,
                    },
                )
            )
        return arguments

    def _to_message(
        self,
        case: Case,
        stage: CourtStage,
        output: AdvocateTurnOutput,
        arguments: List[Argument],
        prefix: str,
    ) -> CourtMessage:
        """The turn as one structured message to the judge"""
        return CourtMessage(
            message_id=f"MSG-{prefix}",
            case_id=case.case_id,
            sender=self.agent_id,
            recipient=JUDGE_AGENT_ID,
            message_type=STAGE_MESSAGE_TYPES[stage],
            stage=stage,
            claim=output.statement,
            argument_ids=[a.argument_id for a in arguments],
            evidence_ids=_unique(eid for a in arguments for eid in a.evidence_ids),
            law_ids=_unique(lid for a in arguments for lid in a.law_ids),
            reasoning=" ".join(f"[{a.argument_id}] {a.claim}" for a in arguments),
        )


def _unique(ids: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(ids))
