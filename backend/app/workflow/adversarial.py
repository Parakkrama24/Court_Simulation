"""The linear trial runner, for custom stage plans

    CASE_INITIALIZATION -> RULE_EVALUATION
    -> EVIDENCE_ANALYSIS
    -> the debate stages you choose, in the order you choose
    -> JURY_INDEPENDENT_DELIBERATION -> JURY_DELIBERATION (optional)
    -> JUDGE_DECISION -> LEGAL_PROCESS_AUDIT -> CASE_COMPLETE

The full procedure of spec section 14 - including JUDGE_QUESTIONS and its
conditional transitions - runs as a LangGraph state machine in ``graph.py``
(``run_court``). This runner stays for research configurations: a debate plan
of any length and order, a repeated stage, the Phase 4-7 trials exactly.

Both run the same steps (``steps.py``), so an agent behaves identically
whichever orchestrates it.
"""

from typing import Any, Dict, List, Optional, Sequence

from app.agents.advocate import (
    REBUTTAL_STAGES,
    STAGE_CODES,
    STAGE_SPEAKERS,
    AdvocateRole,
    AdvocateTurn,
)
from app.agents.evidence import EvidenceAnalysis, EvidenceReview, evidence_context
from app.agents.jury import JurorDecision, JuryResult, JuryRule
from app.domain import Argument, CourtMessage, CourtStage
from app.llm import InteractionLog, LLMProvider

from . import steps
from .common import WorkflowError
from .run import TrialRun
from .steps import MAX_JURORS, CourtOptions, Step

__all__ = [
    "DEFAULT_DEBATE_STAGES",
    "QUICK_DEBATE_STAGES",
    "MAX_JURORS",
    "TrialRun",
    "check_stages",
    "run_adversarial_trial",
]

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

# Openings and closings only: three stages, four advocate calls.
QUICK_DEBATE_STAGES: List[CourtStage] = [
    CourtStage.PROSECUTION_OPENING,
    CourtStage.DEFENSE_OPENING,
    CourtStage.CLOSING_ARGUMENTS,
]


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
    audit: bool = True,
    audit_agent: bool = True,
    auditor_provider: Optional[LLMProvider] = None,
    log: Optional[InteractionLog] = None,
    stages: Optional[Sequence[CourtStage]] = None,
    max_attempts: int = 3,
    strict_engine_alignment: bool = False,
) -> TrialRun:
    """Run a trial along a custom stage plan

    ``provider`` serves every agent unless a per-role provider is given.
    ``evidence=False`` skips the Evidence Agent and drops EVIDENCE_REVIEW from
    the default plan; ``jury=False`` skips the jury; ``audit=False`` skips the
    audit. See ``run_court`` for the full spec section 14 procedure.
    """
    if stages is None:
        stages = [
            s for s in DEFAULT_DEBATE_STAGES if evidence or s != CourtStage.EVIDENCE_REVIEW
        ]
    options = CourtOptions(
        evidence=evidence,
        jury=jury,
        jurors=jurors,
        deliberation=deliberation,
        jury_rule=jury_rule,
        audit=audit,
        audit_agent=audit_agent,
        max_attempts=max_attempts,
        strict_engine_alignment=strict_engine_alignment,
    )
    court = steps.open_court(
        case_id,
        provider,
        prosecution_provider=prosecution_provider,
        defense_provider=defense_provider,
        judge_provider=judge_provider,
        evidence_provider=evidence_provider,
        juror_providers=juror_providers,
        juror_perspectives=juror_perspectives,
        auditor_provider=auditor_provider,
        log=log,
        options=options,
    )
    check_stages(stages, evidence_enabled=evidence)

    events: List[Dict[str, Any]] = list(court.opening_events)
    messages: List[CourtMessage] = []

    def record(step: Step) -> None:
        events.extend(step.events)
        messages.extend(step.messages)

    analysis: Optional[EvidenceAnalysis] = None
    reviews: List[EvidenceReview] = []
    if court.analyst is not None:
        analysis, step = steps.evidence_analysis(court)
        record(step)

    turns: List[AdvocateTurn] = []
    presented: List[Argument] = []
    reviewed: set[str] = set()
    stage_counts: Dict[CourtStage, int] = {}

    for stage in stages:
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        # A repeated stage gets a round number so IDs stay unique.
        round_suffix = "" if stage_counts[stage] == 1 else str(stage_counts[stage])
        context = evidence_context(analysis, reviews)

        if stage == CourtStage.EVIDENCE_REVIEW:
            under_review = [a for a in presented if a.argument_id not in reviewed]
            review, step = steps.evidence_review(
                court, presented, under_review, context, f"MSG-EVIDENCE-REVIEW{round_suffix}"
            )
            reviews.append(review)
            reviewed.update(a.argument_id for a in under_review)
            record(step)
            continue

        for role in STAGE_SPEAKERS[stage]:
            prefix = f"{role.code}-{STAGE_CODES[stage]}{round_suffix}"
            turn, step = steps.advocate_turn(
                court, stage, role, presented, evidence_context(analysis, reviews), prefix
            )
            turns.append(turn)
            presented.extend(turn.arguments)
            record(step)

    context = evidence_context(analysis, reviews)
    independent: List[JurorDecision] = []
    deliberated: List[JurorDecision] = []
    jury_result: Optional[JuryResult] = None
    if jury:
        independent, step = steps.jury_independent(court, presented, context)
        record(step)
        if deliberation and len(court.jurors) > 1:
            deliberated, step = steps.jury_deliberation(court, presented, context, independent)
            record(step)
        jury_result, step = steps.jury_verdict(court, independent, deliberated)
        record(step)

    judgment, agreement, step = steps.judge_decision(court, presented, context, jury_result)
    record(step)

    run = TrialRun(
        case=court.case,
        evaluation=court.evaluation,
        evidence_analysis=analysis,
        evidence_reviews=reviews,
        turns=turns,
        jury_independent=independent,
        jury_deliberation=deliberated,
        jury_result=jury_result,
        judge_jury_agreement=agreement,
        messages=messages,
        judgment=judgment,
        event_history=events,
    )
    if audit:
        run.audit, step = steps.process_audit(court, run)
        run.event_history.extend(step.events)
        run.messages.extend(step.messages)
    run.event_history.append(steps.case_complete(court))
    return run
