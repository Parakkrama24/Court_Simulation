"""Phase 4 workflow: Prosecution <-> Defense -> Judge

    CASE_INITIALIZATION -> RULE_EVALUATION
    -> PROSECUTION_OPENING -> DEFENSE_OPENING
    -> PROSECUTION_ARGUMENT -> DEFENSE_ARGUMENT
    -> PROSECUTION_REBUTTAL -> DEFENSE_REBUTTAL
    -> CLOSING_ARGUMENTS (prosecution, then defense)
    -> JUDGE_DECISION -> CASE_COMPLETE

Each advocate sees the record and every argument presented before its turn,
with court-assigned IDs it can answer. Each turn is one structured
``CourtMessage``. The judge then decides with the full debate in front of it
and must show it weighed both sides.

Stages between arguments and rebuttals in the full procedure (cross
examination, evidence review, judge questions) belong to later phases. The
full procedure, as a LangGraph state machine, replaces this linear runner in
a later phase.
"""

from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.agents.advocate import (
    REBUTTAL_STAGES,
    STAGE_CODES,
    STAGE_SPEAKERS,
    AdvocateAgent,
    AdvocateRole,
    AdvocateTurn,
)
from app.agents.base import add_usage
from app.agents.judge import JudgeAgent, JudgeResult
from app.domain import Argument, Case, CourtMessage, CourtStage, MessageType
from app.llm import InteractionLog, LLMProvider, TokenUsage
from app.rules import CaseEvaluation, LegalRuleRegistry

from .common import WorkflowError, event, prepare_case

DEFAULT_DEBATE_STAGES: List[CourtStage] = [
    CourtStage.PROSECUTION_OPENING,
    CourtStage.DEFENSE_OPENING,
    CourtStage.PROSECUTION_ARGUMENT,
    CourtStage.DEFENSE_ARGUMENT,
    CourtStage.PROSECUTION_REBUTTAL,
    CourtStage.DEFENSE_REBUTTAL,
    CourtStage.CLOSING_ARGUMENTS,
]

# Openings and closings only: three stages, four advocate calls.
QUICK_DEBATE_STAGES: List[CourtStage] = [
    CourtStage.PROSECUTION_OPENING,
    CourtStage.DEFENSE_OPENING,
    CourtStage.CLOSING_ARGUMENTS,
]


class TrialRun(BaseModel):
    """Everything produced by one adversarial trial"""

    case: Case
    evaluation: CaseEvaluation
    turns: List[AdvocateTurn] = Field(default_factory=list)
    messages: List[CourtMessage] = Field(default_factory=list)
    judgment: JudgeResult
    event_history: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def arguments(self) -> List[Argument]:
        """Every argument presented, in order"""
        return [a for turn in self.turns for a in turn.arguments]

    @property
    def prosecution_arguments(self) -> List[Argument]:
        return [a for a in self.arguments if a.agent_id == AdvocateRole.PROSECUTION.agent_id]

    @property
    def defense_arguments(self) -> List[Argument]:
        return [a for a in self.arguments if a.agent_id == AdvocateRole.DEFENSE.agent_id]

    @property
    def usage(self) -> TokenUsage:
        """Tokens across every advocate turn and the judgment"""
        total = self.judgment.usage
        for turn in self.turns:
            total = add_usage(total, turn.usage)
        return total


def check_stages(stages: Sequence[CourtStage]) -> None:
    """Reject a stage plan the debate cannot follow"""
    if not stages:
        raise WorkflowError("A trial needs at least one debate stage")
    spoken: set[AdvocateRole] = set()
    for stage in stages:
        speakers = STAGE_SPEAKERS.get(stage)
        if speakers is None:
            raise WorkflowError(f"{stage.value} is not an adversarial debate stage")
        if stage in REBUTTAL_STAGES and speakers[0].opponent not in spoken:
            raise WorkflowError(
                f"{stage.value} cannot come before the {speakers[0].opponent.value} "
                "has presented any arguments"
            )
        spoken.update(speakers)


def run_adversarial_trial(
    case_id: str,
    provider: Optional[LLMProvider] = None,
    *,
    prosecution_provider: Optional[LLMProvider] = None,
    defense_provider: Optional[LLMProvider] = None,
    judge_provider: Optional[LLMProvider] = None,
    log: Optional[InteractionLog] = None,
    stages: Sequence[CourtStage] = DEFAULT_DEBATE_STAGES,
    max_attempts: int = 3,
    strict_engine_alignment: bool = False,
) -> TrialRun:
    """Run Prosecution <-> Defense -> Judge for one seeded case

    ``provider`` serves every agent unless a per-role provider is given, so the
    two sides - or the judge - can run on different models.
    """
    providers = {
        AdvocateRole.PROSECUTION: prosecution_provider or provider,
        AdvocateRole.DEFENSE: defense_provider or provider,
    }
    judge_llm = judge_provider or provider
    if any(p is None for p in providers.values()) or judge_llm is None:
        raise WorkflowError("Provide `provider`, or a provider for every role")
    check_stages(stages)

    log = log if log is not None else InteractionLog()
    events: List[Dict[str, Any]] = []
    registry = LegalRuleRegistry()
    case, evaluation = prepare_case(case_id, registry, events)

    advocates = {
        role: AdvocateAgent(role, llm, registry=registry, log=log, max_attempts=max_attempts)
        for role, llm in providers.items()
        if llm is not None
    }

    turns: List[AdvocateTurn] = []
    messages: List[CourtMessage] = []
    presented: List[Argument] = []
    stage_counts: Dict[CourtStage, int] = {}

    for stage in stages:
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        # A repeated stage gets a round number so argument IDs stay unique.
        round_suffix = "" if stage_counts[stage] == 1 else str(stage_counts[stage])

        for role in STAGE_SPEAKERS[stage]:
            advocate = advocates[role]
            prefix = f"{role.code}-{STAGE_CODES[stage]}{round_suffix}"
            events.append(event(stage.value, "AGENT_STARTED", agent_id=advocate.agent_id))
            turn = advocate.argue(case, evaluation, stage, presented, id_prefix=prefix)
            turns.append(turn)
            messages.append(turn.message)
            presented.extend(turn.arguments)
            events.append(
                event(
                    stage.value,
                    "AGENT_ARGUMENT",
                    agent_id=advocate.agent_id,
                    message_id=turn.message.message_id,
                    argument_ids=[a.argument_id for a in turn.arguments],
                    responds_to=sorted(
                        {rid for a in turn.arguments for rid in a.counter_argument_ids}
                    ),
                    flags=len(turn.flags),
                    attempts=len(turn.attempts),
                    rejected_attempts=turn.rejected_attempts,
                )
            )

    judge = JudgeAgent(
        judge_llm,
        registry=registry,
        log=log,
        max_attempts=max_attempts,
        strict_engine_alignment=strict_engine_alignment,
    )
    events.append(
        event(CourtStage.JUDGE_DECISION.value, "AGENT_STARTED", agent_id=judge.agent_id)
    )
    judgment = judge.decide(case, evaluation, presented)
    messages.append(
        CourtMessage(
            message_id="MSG-JUDGE-DECISION",
            case_id=case.case_id,
            sender=judge.agent_id,
            recipient="court",
            message_type=MessageType.DECISION,
            stage=CourtStage.JUDGE_DECISION,
            claim=judgment.verdict.decision,
            argument_ids=list(judgment.decision.arguments_considered),
            evidence_ids=list(judgment.verdict.evidence_used),
            law_ids=list(judgment.verdict.laws_used),
            reasoning=judgment.decision.analysis,
        )
    )
    events.append(
        event(
            CourtStage.JUDGE_DECISION.value,
            "JUDGE_DECISION",
            agent_id=judge.agent_id,
            verdict_id=judgment.verdict.verdict_id,
            decision=judgment.verdict.decision,
            arguments_considered=list(judgment.decision.arguments_considered),
            attempts=len(judgment.attempts),
            rejected_attempts=judgment.rejected_attempts,
            divergences=len(judgment.divergences),
        )
    )
    events.append(event(CourtStage.CASE_COMPLETE.value, "CASE_COMPLETE", case_id=case.case_id))

    return TrialRun(
        case=case,
        evaluation=evaluation,
        turns=turns,
        messages=messages,
        judgment=judgment,
        event_history=events,
    )
