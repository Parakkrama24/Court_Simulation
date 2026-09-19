"""Court steps shared by every workflow

A ``Court`` holds what does not change during a trial: the case, the rule
engine's evaluation, the agents, and the options. Each step runs one stage and
returns what it produced plus a ``Step`` - the events and messages to record.
Steps never mutate trial state themselves: the linear runner appends a Step
to its lists, and the LangGraph court returns it as a state update.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.agents.advocate import ANSWER_STAGE, AdvocateAgent, AdvocateRole, AdvocateTurn
from app.agents.auditor import AUDITOR_AGENT_ID, ProcessAudit
from app.agents.evidence import EvidenceAgent, EvidenceAnalysis, EvidenceReview
from app.agents.judge import JudgeAgent, JudgeQuestionRound, JudgeResult
from app.agents.jury import (
    JurorAgent,
    JurorDecision,
    JuryResult,
    JuryRule,
    aggregate_jury,
    judge_jury_agreement,
    jury_context,
)
from app.domain import Argument, Case, CourtMessage, CourtStage, JudgeQuestion, MessageType
from app.llm import InteractionLog, LLMProvider
from app.rules import CaseEvaluation, LegalRuleRegistry

from .audit import audit_trial
from .common import WorkflowError, event, prepare_case
from .run import TrialRun

MAX_JURORS = 12


@dataclass
class CourtOptions:
    """Which parts of the procedure run, and how"""

    evidence: bool = True
    cross_examination: bool = True
    judge_questions: bool = True
    max_question_rounds: int = 1
    jury: bool = True
    jurors: int = 3
    deliberation: bool = True
    jury_rule: JuryRule = JuryRule.UNANIMOUS
    audit: bool = True
    audit_agent: bool = True
    max_attempts: int = 3
    strict_engine_alignment: bool = False


@dataclass
class Court:
    """Everything about a trial that does not change while it runs"""

    case: Case
    evaluation: CaseEvaluation
    registry: LegalRuleRegistry
    log: InteractionLog
    options: CourtOptions
    advocates: Dict[AdvocateRole, AdvocateAgent]
    judge: JudgeAgent
    analyst: Optional[EvidenceAgent] = None
    jurors: List[JurorAgent] = field(default_factory=list)
    auditor_llm: Optional[LLMProvider] = None
    opening_events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Step:
    """What one step adds to the trial record"""

    events: List[Dict[str, Any]] = field(default_factory=list)
    messages: List[CourtMessage] = field(default_factory=list)


def open_court(
    case_id: str,
    provider: Optional[LLMProvider] = None,
    *,
    prosecution_provider: Optional[LLMProvider] = None,
    defense_provider: Optional[LLMProvider] = None,
    judge_provider: Optional[LLMProvider] = None,
    evidence_provider: Optional[LLMProvider] = None,
    juror_providers: Optional[Sequence[LLMProvider]] = None,
    juror_perspectives: Optional[Sequence[Optional[str]]] = None,
    auditor_provider: Optional[LLMProvider] = None,
    log: Optional[InteractionLog] = None,
    options: Optional[CourtOptions] = None,
) -> Court:
    """Check the configuration, load the case, and seat the agents

    ``provider`` serves every agent without its own provider. Every problem
    with the configuration is raised here, before any model is called.
    """
    options = options or CourtOptions()
    llms = {
        AdvocateRole.PROSECUTION: prosecution_provider or provider,
        AdvocateRole.DEFENSE: defense_provider or provider,
    }
    judge_llm = judge_provider or provider
    evidence_llm = evidence_provider or provider

    missing = [role.value for role, llm in llms.items() if llm is None]
    if judge_llm is None:
        missing.append("judge")
    if options.evidence and evidence_llm is None:
        missing.append("evidence")
    juror_llms: List[Optional[LLMProvider]] = []
    if options.jury:
        if not 1 <= options.jurors <= MAX_JURORS:
            raise WorkflowError(f"A jury needs between 1 and {MAX_JURORS} jurors")
        for name, values in (
            ("juror_providers", juror_providers),
            ("juror_perspectives", juror_perspectives),
        ):
            if values is not None and len(values) != options.jurors:
                raise WorkflowError(
                    f"{name} has {len(values)} entries for {options.jurors} jurors"
                )
        juror_llms = list(juror_providers) if juror_providers else [provider] * options.jurors
        if any(llm is None for llm in juror_llms):
            missing.append("jury")
    if missing:
        raise WorkflowError(
            f"Provide `provider`, or a provider for every role (missing: {', '.join(missing)})"
        )
    if options.max_question_rounds < 0:
        raise WorkflowError("max_question_rounds cannot be negative")
    assert judge_llm is not None  # checked above

    log = log if log is not None else InteractionLog()
    registry = LegalRuleRegistry()
    opening_events: List[Dict[str, Any]] = []
    case, evaluation = prepare_case(case_id, registry, opening_events)
    attempts = options.max_attempts

    perspectives = list(juror_perspectives) if juror_perspectives else [None] * options.jurors
    return Court(
        case=case,
        evaluation=evaluation,
        registry=registry,
        log=log,
        options=options,
        advocates={
            role: AdvocateAgent(role, llm, registry=registry, log=log, max_attempts=attempts)
            for role, llm in llms.items()
            if llm is not None
        },
        judge=JudgeAgent(
            judge_llm,
            registry=registry,
            log=log,
            max_attempts=attempts,
            strict_engine_alignment=options.strict_engine_alignment,
        ),
        analyst=(
            EvidenceAgent(evidence_llm, registry=registry, log=log, max_attempts=attempts)
            if options.evidence and evidence_llm is not None
            else None
        ),
        jurors=[
            JurorAgent(
                f"jury_{index + 1}",
                llm,
                registry=registry,
                log=log,
                max_attempts=attempts,
                perspective=perspectives[index],
            )
            for index, llm in enumerate(juror_llms)
            if llm is not None
        ],
        auditor_llm=(auditor_provider or provider) if options.audit_agent else None,
        opening_events=opening_events,
    )


# ============================================================================
# Steps
# ============================================================================


def stage_skipped(stage: CourtStage, reason: str) -> Dict[str, Any]:
    """Record that a stage of the procedure did not run, and why"""
    return event(stage.value, "STAGE_SKIPPED", reason=reason)


def evidence_analysis(court: Court) -> Tuple[EvidenceAnalysis, Step]:
    """EVIDENCE_ANALYSIS"""
    assert court.analyst is not None
    stage = CourtStage.EVIDENCE_ANALYSIS.value
    started = event(stage, "AGENT_STARTED", agent_id=court.analyst.agent_id)
    analysis = court.analyst.analyze(court.case, court.evaluation)
    claims = analysis.output.claims
    done = event(
        stage,
        "EVIDENCE_ANALYZED",
        agent_id=court.analyst.agent_id,
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
    return analysis, Step([started, done], [analysis.message])


def advocate_turn(
    court: Court,
    stage: CourtStage,
    role: AdvocateRole,
    presented: Sequence[Argument],
    context: Optional[Dict[str, Any]],
    id_prefix: str,
    questions: Sequence[JudgeQuestion] = (),
) -> Tuple[AdvocateTurn, Step]:
    """One advocate turn at a debate stage, or an answer to the judge"""
    advocate = court.advocates[role]
    started = event(stage.value, "AGENT_STARTED", agent_id=advocate.agent_id)
    turn = advocate.argue(
        court.case,
        court.evaluation,
        stage,
        presented,
        id_prefix=id_prefix,
        evidence_context=context,
        questions=questions,
    )
    responds_to = sorted({rid for a in turn.arguments for rid in a.counter_argument_ids})
    details: Dict[str, Any] = dict(
        agent_id=advocate.agent_id,
        message_id=turn.message.message_id,
        argument_ids=[a.argument_id for a in turn.arguments],
        responds_to=responds_to,
        flags=len(turn.flags),
        attempts=len(turn.attempts),
        rejected_attempts=turn.rejected_attempts,
    )
    if stage == ANSWER_STAGE:
        # Spec section 21: AGENT_RESPONSE for a party answering the court.
        details["answered"] = [
            q.question_id for q in questions if q.question_id in responds_to
        ]
        done = event(stage.value, "AGENT_RESPONSE", **details)
    else:
        done = event(stage.value, "AGENT_ARGUMENT", **details)
    return turn, Step([started, done], [turn.message])


def evidence_review(
    court: Court,
    presented: Sequence[Argument],
    under_review: Sequence[Argument],
    context: Optional[Dict[str, Any]],
    message_id: str,
    questions: Sequence[JudgeQuestion] = (),
) -> Tuple[EvidenceReview, Step]:
    """EVIDENCE_REVIEW of the arguments not yet reviewed"""
    assert court.analyst is not None
    stage = CourtStage.EVIDENCE_REVIEW.value
    started = event(stage, "AGENT_STARTED", agent_id=court.analyst.agent_id)
    review = court.analyst.review(
        court.case,
        court.evaluation,
        presented,
        under_review,
        message_id=message_id,
        evidence_context=context,
        judge_questions=questions,
    )
    done = event(
        stage,
        "EVIDENCE_REVIEWED",
        agent_id=court.analyst.agent_id,
        reviewed=[a.argument_id for a in under_review],
        unsupported=review.unsupported_argument_ids,
        flags=len(review.flags),
        attempts=len(review.attempts),
        rejected_attempts=review.rejected_attempts,
    )
    return review, Step([started, done], [review.message])


def judge_questions(
    court: Court,
    presented: Sequence[Argument],
    flagged: Sequence[str],
    round_number: int,
    context: Optional[Dict[str, Any]],
    earlier: Sequence[JudgeQuestion] = (),
) -> Tuple[JudgeQuestionRound, Step]:
    """JUDGE_QUESTIONS: the judge questions parties about unsupported arguments"""
    stage = CourtStage.JUDGE_QUESTIONS.value
    started = event(stage, "AGENT_STARTED", agent_id=court.judge.agent_id)
    question_round = court.judge.ask_questions(
        court.case,
        court.evaluation,
        presented,
        flagged,
        round_number=round_number,
        evidence_context=context,
        earlier_questions=earlier,
    )
    done = event(
        stage,
        "JUDGE_QUESTION",  # spec section 21
        agent_id=court.judge.agent_id,
        round=round_number,
        flagged=list(flagged),
        questions={q.question_id: q.addressed_to for q in question_round.questions},
        attempts=len(question_round.attempts),
        rejected_attempts=question_round.rejected_attempts,
    )
    return question_round, Step([started, done], [question_round.message])


def jury_independent(
    court: Court,
    presented: Sequence[Argument],
    context: Optional[Dict[str, Any]],
    questions: Sequence[JudgeQuestion] = (),
) -> Tuple[List[JurorDecision], Step]:
    """JURY_INDEPENDENT_DELIBERATION: each juror decides from the record alone"""
    stage = CourtStage.JURY_INDEPENDENT_DELIBERATION.value
    decisions: List[JurorDecision] = []
    step = Step()
    for juror in court.jurors:
        step.events.append(event(stage, "AGENT_STARTED", agent_id=juror.juror_id))
        # Built from the trial record alone: no other juror's view is an input.
        decision = juror.decide_independently(
            court.case, court.evaluation, presented, context, questions
        )
        decisions.append(decision)
        step.messages.append(decision.message)
        step.events.append(
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
    return decisions, step


def jury_deliberation(
    court: Court,
    presented: Sequence[Argument],
    context: Optional[Dict[str, Any]],
    independent: Sequence[JurorDecision],
    questions: Sequence[JudgeQuestion] = (),
) -> Tuple[List[JurorDecision], Step]:
    """JURY_DELIBERATION: each juror reconsiders once, seeing the whole panel"""
    stage = CourtStage.JURY_DELIBERATION.value
    panel = {d.juror_id: d.output for d in independent}
    decisions: List[JurorDecision] = []
    step = Step()
    for juror in court.jurors:
        step.events.append(event(stage, "AGENT_STARTED", agent_id=juror.juror_id))
        decision = juror.deliberate(
            court.case, court.evaluation, presented, context, panel, questions
        )
        decisions.append(decision)
        step.messages.append(decision.message)
        step.events.append(
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
    return decisions, step


def jury_verdict(
    court: Court,
    independent: Sequence[JurorDecision],
    deliberation: Sequence[JurorDecision],
) -> Tuple[JuryResult, Step]:
    """The verdict engine tallies the final round"""
    result = aggregate_jury(
        {d.juror_id: d.output for d in independent},
        court.case.charges,
        court.options.jury_rule,
        deliberation={d.juror_id: d.output for d in deliberation} or None,
    )
    stage = (
        CourtStage.JURY_DELIBERATION if deliberation else CourtStage.JURY_INDEPENDENT_DELIBERATION
    ).value
    done = event(
        stage,
        "JURY_VERDICT",
        rule=court.options.jury_rule.value,
        verdicts={t.charge: t.outcome.value for t in result.final},
        independent_agreement=result.independent_agreement,
        final_agreement=result.final_agreement,
        vote_changes=len(result.vote_changes),
    )
    return result, Step([done])


def judge_decision(
    court: Court,
    presented: Sequence[Argument],
    context: Optional[Dict[str, Any]],
    jury_result: Optional[JuryResult],
    questions: Sequence[JudgeQuestion] = (),
) -> Tuple[JudgeResult, List[Dict[str, Any]], Step]:
    """JUDGE_DECISION, and how it compares with the jury"""
    stage = CourtStage.JUDGE_DECISION.value
    started = event(stage, "AGENT_STARTED", agent_id=court.judge.agent_id)
    judgment = court.judge.decide(
        court.case,
        court.evaluation,
        presented,
        evidence_context=context,
        jury_context=jury_context(jury_result) if jury_result else None,
        judge_questions=questions,
    )
    agreement = (
        judge_jury_agreement(
            {c.charge: c.decision for c in judgment.decision.charge_decisions}, jury_result
        )
        if jury_result
        else []
    )
    message = CourtMessage(
        message_id="MSG-JUDGE-DECISION",
        case_id=court.case.case_id,
        sender=court.judge.agent_id,
        recipient="court",
        message_type=MessageType.DECISION,
        stage=CourtStage.JUDGE_DECISION,
        claim=judgment.verdict.decision,
        argument_ids=list(judgment.decision.arguments_considered),
        evidence_ids=list(judgment.verdict.evidence_used),
        law_ids=list(judgment.verdict.laws_used),
        reasoning=judgment.decision.analysis,
    )
    done = event(
        stage,
        "JUDGE_DECISION",
        agent_id=court.judge.agent_id,
        verdict_id=judgment.verdict.verdict_id,
        decision=judgment.verdict.decision,
        arguments_considered=list(judgment.decision.arguments_considered),
        attempts=len(judgment.attempts),
        rejected_attempts=judgment.rejected_attempts,
        divergences=len(judgment.divergences),
        agrees_with_jury={row["charge"]: row["agrees"] for row in agreement},
    )
    return judgment, agreement, Step([started, done], [message])


def process_audit(court: Court, run: TrialRun) -> Tuple[ProcessAudit, Step]:
    """LEGAL_PROCESS_AUDIT of the trial so far"""
    stage = CourtStage.LEGAL_PROCESS_AUDIT.value
    started = event(stage, "AGENT_STARTED", agent_id=AUDITOR_AGENT_ID)
    # The auditor sees the audit stage itself as part of the trial.
    probe = run.model_copy(update={"event_history": run.event_history + [started]})
    audit = audit_trial(
        probe, court.auditor_llm, log=court.log, max_attempts=court.options.max_attempts
    )
    report = audit.report
    message = CourtMessage(
        message_id="MSG-AUDIT-REPORT",
        case_id=court.case.case_id,
        sender=AUDITOR_AGENT_ID,
        recipient="court",
        message_type=MessageType.AUDIT_REPORT,
        stage=CourtStage.LEGAL_PROCESS_AUDIT,
        claim=report.final_assessment,
        reasoning=f"Overall status: {report.metadata['overall_status']}",
    )
    done = event(
        stage,
        "AUDIT_COMPLETED",
        agent_id=AUDITOR_AGENT_ID,
        audit_id=report.audit_id,
        overall_status=report.metadata["overall_status"],
        severity_counts=report.metadata["severity_counts"],
        findings=len(audit.findings),
        deterministic_only=report.metadata["deterministic_only"],
    )
    return audit, Step([started, done], [message])


def case_complete(court: Court) -> Dict[str, Any]:
    return event(CourtStage.CASE_COMPLETE.value, "CASE_COMPLETE", case_id=court.case.case_id)
