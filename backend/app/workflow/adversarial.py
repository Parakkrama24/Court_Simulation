"""Adversarial trial: Evidence -> Prosecution <-> Defense -> Jury -> Judge

    CASE_INITIALIZATION -> RULE_EVALUATION
    -> EVIDENCE_ANALYSIS                                    (Phase 5)
    -> PROSECUTION_OPENING -> DEFENSE_OPENING
    -> PROSECUTION_ARGUMENT -> DEFENSE_ARGUMENT
    -> EVIDENCE_REVIEW                                      (Phase 5)
    -> PROSECUTION_REBUTTAL -> DEFENSE_REBUTTAL
    -> CLOSING_ARGUMENTS (prosecution, then defense)
    -> JURY_INDEPENDENT_DELIBERATION                        (Phase 6)
    -> JURY_DELIBERATION (optional)                         (Phase 6)
    -> JUDGE_DECISION -> CASE_COMPLETE

The neutral Evidence Agent analyses the record before anyone argues, and
reviews the parties' arguments where spec section 14 places EVIDENCE_REVIEW.
Its work is added to the record every later speaker - advocates and judge -
sees. Each advocate also sees every argument presented before its turn, with
court-assigned IDs it can answer. Every turn is one structured
``CourtMessage``.

After closing arguments each juror decides independently - its request is
built from the trial record alone, so no other juror's view can reach it -
then, optionally, reconsiders once with the whole panel's decisions in view.
The verdict engine tallies the votes. The judge decides last, with the jury's
result in front of it, and must show it weighed both sides.

Cross examination and judge questions are not yet implemented. The full
procedure, as a LangGraph state machine, replaces this linear runner in a
later phase.
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
from app.agents.evidence import (
    EvidenceAgent,
    EvidenceAnalysis,
    EvidenceReview,
    evidence_context,
)
from app.agents.judge import JudgeAgent, JudgeResult
from app.agents.jury import (
    JurorAgent,
    JurorDecision,
    JuryResult,
    JuryRule,
    aggregate_jury,
    judge_jury_agreement,
    jury_context,
)
from app.domain import Argument, Case, CourtMessage, CourtStage, MessageType
from app.llm import InteractionLog, LLMProvider, TokenUsage
from app.rules import CaseEvaluation, LegalRuleRegistry

from .common import WorkflowError, event, prepare_case

DEFAULT_DEBATE_STAGES: List[CourtStage] = [
    CourtStage.PROSECUTION_OPENING,
    CourtStage.DEFENSE_OPENING,
    CourtStage.PROSECUTION_ARGUMENT,
    CourtStage.DEFENSE_ARGUMENT,
    CourtStage.EVIDENCE_REVIEW,
    CourtStage.PROSECUTION_REBUTTAL,
    CourtStage.DEFENSE_REBUTTAL,
    CourtStage.CLOSING_ARGUMENTS,
]

MAX_JURORS = 12

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
    evidence_analysis: Optional[EvidenceAnalysis] = None
    evidence_reviews: List[EvidenceReview] = Field(default_factory=list)
    turns: List[AdvocateTurn] = Field(default_factory=list)
    jury_independent: List[JurorDecision] = Field(default_factory=list)
    jury_deliberation: List[JurorDecision] = Field(default_factory=list)
    jury_result: Optional[JuryResult] = None
    judge_jury_agreement: List[Dict[str, Any]] = Field(default_factory=list)
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
        """Tokens across every agent call in the trial"""
        total = self.judgment.usage
        for turn in self.turns:
            total = add_usage(total, turn.usage)
        if self.evidence_analysis is not None:
            total = add_usage(total, self.evidence_analysis.usage)
        for review in self.evidence_reviews:
            total = add_usage(total, review.usage)
        for decision in self.jury_independent + self.jury_deliberation:
            total = add_usage(total, decision.usage)
        return total

    @property
    def jury_verdicts(self) -> List[Any]:
        """Every juror's domain Verdict: independent round, then deliberation"""
        return [d.verdict for d in self.jury_independent + self.jury_deliberation]


def check_stages(stages: Sequence[CourtStage], evidence_enabled: bool = True) -> None:
    """Reject a stage plan the trial cannot follow, before any model is called"""
    if not stages:
        raise WorkflowError("A trial needs at least one debate stage")
    spoken: set[AdvocateRole] = set()
    new_since_review = False
    for stage in stages:
        if stage == CourtStage.EVIDENCE_REVIEW:
            if not evidence_enabled:
                raise WorkflowError("EVIDENCE_REVIEW needs the Evidence Agent to be enabled")
            if not new_since_review:
                raise WorkflowError(
                    "EVIDENCE_REVIEW needs at least one argument presented since the last review"
                )
            new_since_review = False
            continue

        speakers = STAGE_SPEAKERS.get(stage)
        if speakers is None:
            raise WorkflowError(f"{stage.value} is not an adversarial debate stage")
        if stage in REBUTTAL_STAGES and speakers[0].opponent not in spoken:
            raise WorkflowError(
                f"{stage.value} cannot come before the {speakers[0].opponent.value} "
                "has presented any arguments"
            )
        spoken.update(speakers)
        new_since_review = True


def run_adversarial_trial(
    case_id: str,
    provider: Optional[LLMProvider] = None,
    *,
    prosecution_provider: Optional[LLMProvider] = None,
    defense_provider: Optional[LLMProvider] = None,
    judge_provider: Optional[LLMProvider] = None,
    evidence_provider: Optional[LLMProvider] = None,
    evidence: bool = True,
    jury: bool = True,
    jurors: int = 3,
    juror_providers: Optional[Sequence[LLMProvider]] = None,
    juror_perspectives: Optional[Sequence[Optional[str]]] = None,
    deliberation: bool = True,
    jury_rule: JuryRule = JuryRule.UNANIMOUS,
    log: Optional[InteractionLog] = None,
    stages: Optional[Sequence[CourtStage]] = None,
    max_attempts: int = 3,
    strict_engine_alignment: bool = False,
) -> TrialRun:
    """Run the adversarial trial for one seeded case

    ``provider`` serves every agent unless a per-role provider is given, so the
    two sides, the evidence analyst, or the judge can run on different models.
    With ``evidence=False`` the Evidence Agent is skipped entirely and the
    default plan drops EVIDENCE_REVIEW (the Phase 4 trial).

    With ``jury=True`` (the default) ``jurors`` jurors decide independently
    after closing arguments, then - if ``deliberation`` - reconsider once as a
    panel. Each juror uses ``juror_providers[i]`` if given, else ``provider``,
    and ``juror_perspectives[i]`` as an optional background for research
    configurations; by default all jurors get identical instructions.
    """
    providers = {
        AdvocateRole.PROSECUTION: prosecution_provider or provider,
        AdvocateRole.DEFENSE: defense_provider or provider,
    }
    judge_llm = judge_provider or provider
    evidence_llm = evidence_provider or provider
    missing = [role.value for role, llm in providers.items() if llm is None]
    if judge_llm is None:
        missing.append("judge")
    if evidence and evidence_llm is None:
        missing.append("evidence")
    if jury:
        if not 1 <= jurors <= MAX_JURORS:
            raise WorkflowError(f"A jury needs between 1 and {MAX_JURORS} jurors")
        for name, values in (("juror_providers", juror_providers),
                             ("juror_perspectives", juror_perspectives)):
            if values is not None and len(values) != jurors:
                raise WorkflowError(f"{name} has {len(values)} entries for {jurors} jurors")
        juror_llms = list(juror_providers) if juror_providers else [provider] * jurors
        if any(llm is None for llm in juror_llms):
            missing.append("jury")
    if missing:
        raise WorkflowError(
            f"Provide `provider`, or a provider for every role (missing: {', '.join(missing)})"
        )

    if stages is None:
        stages = [
            s for s in DEFAULT_DEBATE_STAGES if evidence or s != CourtStage.EVIDENCE_REVIEW
        ]
    check_stages(stages, evidence_enabled=evidence)

    log = log if log is not None else InteractionLog()
    events: List[Dict[str, Any]] = []
    registry = LegalRuleRegistry()
    case, evaluation = prepare_case(case_id, registry, events)
    messages: List[CourtMessage] = []

    # -- EVIDENCE_ANALYSIS -------------------------------------------------
    analyst: Optional[EvidenceAgent] = None
    analysis: Optional[EvidenceAnalysis] = None
    reviews: List[EvidenceReview] = []
    if evidence and evidence_llm is not None:
        analyst = EvidenceAgent(evidence_llm, registry=registry, log=log, max_attempts=max_attempts)
        events.append(
            event(CourtStage.EVIDENCE_ANALYSIS.value, "AGENT_STARTED", agent_id=analyst.agent_id)
        )
        analysis = analyst.analyze(case, evaluation)
        messages.append(analysis.message)
        claims = analysis.output.claims
        events.append(
            event(
                CourtStage.EVIDENCE_ANALYSIS.value,
                "EVIDENCE_ANALYZED",
                agent_id=analyst.agent_id,
                claims={
                    status: sum(1 for c in claims if c.status.value == status)
                    for status in ("established", "disputed", "unsupported")
                },
                contradictions=len(analysis.output.contradictions),
                missing_evidence=len(analysis.output.missing_evidence),
                flags=len(analysis.flags),
                attempts=len(analysis.attempts),
                rejected_attempts=analysis.rejected_attempts,
            )
        )

    # -- The debate ----------------------------------------------------------
    advocates = {
        role: AdvocateAgent(role, llm, registry=registry, log=log, max_attempts=max_attempts)
        for role, llm in providers.items()
        if llm is not None
    }
    turns: List[AdvocateTurn] = []
    presented: List[Argument] = []
    reviewed: set[str] = set()
    stage_counts: Dict[CourtStage, int] = {}

    for stage in stages:
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        # A repeated stage gets a round number so IDs stay unique.
        round_suffix = "" if stage_counts[stage] == 1 else str(stage_counts[stage])

        if stage == CourtStage.EVIDENCE_REVIEW:
            assert analyst is not None  # guaranteed by check_stages
            under_review = [a for a in presented if a.argument_id not in reviewed]
            events.append(event(stage.value, "AGENT_STARTED", agent_id=analyst.agent_id))
            review = analyst.review(
                case,
                evaluation,
                presented,
                under_review,
                message_id=f"MSG-EVIDENCE-REVIEW{round_suffix}",
                evidence_context=evidence_context(analysis, reviews),
            )
            reviews.append(review)
            messages.append(review.message)
            reviewed.update(a.argument_id for a in under_review)
            events.append(
                event(
                    stage.value,
                    "EVIDENCE_REVIEWED",
                    agent_id=analyst.agent_id,
                    reviewed=[a.argument_id for a in under_review],
                    unsupported=review.unsupported_argument_ids,
                    flags=len(review.flags),
                    attempts=len(review.attempts),
                    rejected_attempts=review.rejected_attempts,
                )
            )
            continue

        for role in STAGE_SPEAKERS[stage]:
            advocate = advocates[role]
            prefix = f"{role.code}-{STAGE_CODES[stage]}{round_suffix}"
            events.append(event(stage.value, "AGENT_STARTED", agent_id=advocate.agent_id))
            turn = advocate.argue(
                case,
                evaluation,
                stage,
                presented,
                id_prefix=prefix,
                evidence_context=evidence_context(analysis, reviews),
            )
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

    # -- JURY_INDEPENDENT_DELIBERATION / JURY_DELIBERATION ----------------------
    jury_independent: List[JurorDecision] = []
    jury_deliberation: List[JurorDecision] = []
    jury_result: Optional[JuryResult] = None
    shared = evidence_context(analysis, reviews)
    if jury:
        perspectives = list(juror_perspectives) if juror_perspectives else [None] * jurors
        panel_agents = [
            JurorAgent(
                f"jury_{index + 1}",
                llm,
                registry=registry,
                log=log,
                max_attempts=max_attempts,
                perspective=perspectives[index],
            )
            for index, llm in enumerate(juror_llms)
            if llm is not None
        ]

        stage = CourtStage.JURY_INDEPENDENT_DELIBERATION.value
        for juror in panel_agents:
            events.append(event(stage, "AGENT_STARTED", agent_id=juror.juror_id))
            # Built from the trial record alone: no other juror's view is an input.
            decision = juror.decide_independently(case, evaluation, presented, shared)
            jury_independent.append(decision)
            messages.append(decision.message)
            events.append(
                event(
                    stage,
                    "JURY_DECISION",
                    agent_id=juror.juror_id,
                    round="independent",
                    decision=decision.verdict.decision,
                    confidence=decision.output.confidence,
                    attempts=len(decision.attempts),
                    rejected_attempts=decision.rejected_attempts,
                )
            )

        panel = {d.juror_id: d.output for d in jury_independent}
        if deliberation and len(panel_agents) > 1:
            stage = CourtStage.JURY_DELIBERATION.value
            for juror in panel_agents:
                events.append(event(stage, "AGENT_STARTED", agent_id=juror.juror_id))
                decision = juror.deliberate(case, evaluation, presented, shared, panel)
                jury_deliberation.append(decision)
                messages.append(decision.message)
                events.append(
                    event(
                        stage,
                        "JURY_DECISION",
                        agent_id=juror.juror_id,
                        round="deliberation",
                        decision=decision.verdict.decision,
                        changed_charges=decision.changed_charges,
                        attempts=len(decision.attempts),
                        rejected_attempts=decision.rejected_attempts,
                    )
                )

        jury_result = aggregate_jury(
            panel,
            case.charges,
            jury_rule,
            deliberation={d.juror_id: d.output for d in jury_deliberation} or None,
        )
        events.append(
            event(
                stage,
                "JURY_VERDICT",
                rule=jury_rule.value,
                verdicts={t.charge: t.outcome.value for t in jury_result.final},
                independent_agreement=jury_result.independent_agreement,
                final_agreement=jury_result.final_agreement,
                vote_changes=len(jury_result.vote_changes),
            )
        )

    # -- JUDGE_DECISION ------------------------------------------------------
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
    judgment = judge.decide(
        case,
        evaluation,
        presented,
        evidence_context=shared,
        jury_context=jury_context(jury_result) if jury_result else None,
    )
    agreement = (
        judge_jury_agreement(
            {c.charge: c.decision for c in judgment.decision.charge_decisions}, jury_result
        )
        if jury_result
        else []
    )
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
            agrees_with_jury={row["charge"]: row["agrees"] for row in agreement},
        )
    )
    events.append(event(CourtStage.CASE_COMPLETE.value, "CASE_COMPLETE", case_id=case.case_id))

    return TrialRun(
        case=case,
        evaluation=evaluation,
        evidence_analysis=analysis,
        evidence_reviews=reviews,
        turns=turns,
        jury_independent=jury_independent,
        jury_deliberation=jury_deliberation,
        jury_result=jury_result,
        judge_jury_agreement=agreement,
        messages=messages,
        judgment=judgment,
        event_history=events,
    )
