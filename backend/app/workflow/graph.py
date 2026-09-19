"""The full court procedure as a LangGraph state machine (spec section 14)

    CASE_INITIALIZATION
      -> EVIDENCE_ANALYSIS ....................... if the Evidence Agent is on
      -> PROSECUTION_OPENING -> DEFENSE_OPENING
      -> PROSECUTION_ARGUMENT -> DEFENSE_ARGUMENT
      -> CROSS_EXAMINATION ....................... if enabled
      -> EVIDENCE_REVIEW ......................... if the Evidence Agent is on
           |-- an argument is unsupported? --> JUDGE_QUESTIONS -> answers
           |                                     -> review of the answers --+
           |<------- still unsupported, rounds remain --------------------+
      -> PROSECUTION_REBUTTAL -> DEFENSE_REBUTTAL
      -> CLOSING_ARGUMENTS
      -> JURY_INDEPENDENT_DELIBERATION ........... if the jury is on
      -> JURY_DELIBERATION ....................... if on, with 2+ jurors
      -> JUDGE_DECISION
      -> LEGAL_PROCESS_AUDIT ..................... if the audit is on
      -> CASE_COMPLETE

Conditional transitions decide which branch runs. The one the spec names -
"the Judge should be able to request additional analysis if an argument
lacks evidence" - is the loop above: when the evidence review finds an
argument unsupported, the judge questions the party that made it, the party
answers, and the Evidence Agent reviews the answers. The loop is bounded by
``max_question_rounds``.

Every node runs a step from ``steps.py`` - the same steps the linear runner
uses - and returns only what it adds to the state. A stage that does not run
is recorded as a ``STAGE_SKIPPED`` event with the reason, so the audit can
tell "not needed" from "left out".
"""

import operator
from typing import Annotated, Any, Callable, Dict, List, Optional, Sequence, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.advocate import (
    ANSWER_STAGE,
    STAGE_CODES,
    STAGE_SPEAKERS,
    AdvocateRole,
    AdvocateTurn,
)
from app.agents.auditor import ProcessAudit
from app.agents.evidence import EvidenceAnalysis, EvidenceReview, evidence_context
from app.agents.judge import JudgeQuestionRound, JudgeResult
from app.agents.jury import JurorDecision, JuryResult, JuryRule
from app.domain import (
    Argument,
    AuditReport,
    Case,
    CourtMessage,
    CourtStage,
    Evidence,
    Fact,
    JudgeQuestion,
    LegalRule,
    Verdict,
)
from app.llm import InteractionLog, LLMProvider
from app.rules import CaseEvaluation

from . import steps
from .run import TrialRun
from .steps import Court, CourtOptions, Step

# The full procedure is ~20 steps plus question rounds; LangGraph's default
# recursion limit (25) is too tight for it.
RECURSION_LIMIT = 200


class CourtState(TypedDict, total=False):
    """The state of one trial as it moves through the procedure

    The first block is spec section 17's minimum. List fields marked with
    ``operator.add`` are append-only: a node returns only what it adds.
    """

    # -- spec section 17 -------------------------------------------------------
    case: Case
    current_stage: str
    facts: List[Fact]
    evidence: List[Evidence]
    applicable_laws: List[LegalRule]
    prosecution_arguments: Annotated[List[Argument], operator.add]
    defense_arguments: Annotated[List[Argument], operator.add]
    evidence_analysis: Optional[EvidenceAnalysis]
    judge_questions: Annotated[List[JudgeQuestion], operator.add]
    jury_decisions: Annotated[List[Verdict], operator.add]
    judge_decision: Optional[Verdict]
    audit_report: Optional[AuditReport]
    event_history: Annotated[List[Dict[str, Any]], operator.add]

    # -- working state --------------------------------------------------------
    evaluation: CaseEvaluation
    arguments: Annotated[List[Argument], operator.add]  # both sides, in order
    turns: Annotated[List[AdvocateTurn], operator.add]
    messages: Annotated[List[CourtMessage], operator.add]
    evidence_reviews: Annotated[List[EvidenceReview], operator.add]
    reviewed_ids: Annotated[List[str], operator.add]
    question_rounds: Annotated[List[JudgeQuestionRound], operator.add]
    pending_flagged: List[str]  # unsupported arguments awaiting the judge's questions
    jury_independent: Annotated[List[JurorDecision], operator.add]
    jury_deliberation: Annotated[List[JurorDecision], operator.add]
    jury_result: Optional[JuryResult]
    judgment: Optional[JudgeResult]
    judge_jury_agreement: List[Dict[str, Any]]
    audit: Optional[ProcessAudit]


Node = Callable[[CourtState], Dict[str, Any]]


def _update(stage: CourtStage, step: Step, **fields: Any) -> Dict[str, Any]:
    """A node's state update: its stage, its events and messages, and its fields"""
    return {
        "current_stage": stage.value,
        "event_history": list(step.events),
        "messages": list(step.messages),
        **fields,
    }


def _context(state: CourtState) -> Optional[Dict[str, Any]]:
    return evidence_context(state.get("evidence_analysis"), state.get("evidence_reviews", []))


def _split(arguments: Sequence[Argument]) -> Dict[str, List[Argument]]:
    return {
        "arguments": list(arguments),
        "prosecution_arguments": [
            a for a in arguments if a.agent_id == AdvocateRole.PROSECUTION.agent_id
        ],
        "defense_arguments": [a for a in arguments if a.agent_id == AdvocateRole.DEFENSE.agent_id],
    }


def run_from_state(state: CourtState) -> TrialRun:
    """The TrialRun a (finished or partial) court state describes"""
    judgment = state.get("judgment")
    if judgment is None:
        raise ValueError("The court has not reached a judgment yet")
    return TrialRun(
        case=state["case"],
        evaluation=state["evaluation"],
        evidence_analysis=state.get("evidence_analysis"),
        evidence_reviews=list(state.get("evidence_reviews", [])),
        turns=list(state.get("turns", [])),
        judge_question_rounds=list(state.get("question_rounds", [])),
        jury_independent=list(state.get("jury_independent", [])),
        jury_deliberation=list(state.get("jury_deliberation", [])),
        jury_result=state.get("jury_result"),
        judge_jury_agreement=list(state.get("judge_jury_agreement", [])),
        messages=list(state.get("messages", [])),
        judgment=judgment,
        audit=state.get("audit"),
        event_history=list(state.get("event_history", [])),
    )


# ============================================================================
# Nodes
# ============================================================================


def _case_initialization(court: Court) -> Node:
    def node(state: CourtState) -> Dict[str, Any]:
        options = court.options
        skipped: List[Dict[str, Any]] = []
        off = "disabled in this run's configuration"
        if court.analyst is None:
            skipped.append(steps.stage_skipped(CourtStage.EVIDENCE_ANALYSIS, off))
            skipped.append(steps.stage_skipped(CourtStage.EVIDENCE_REVIEW, off))
        if not options.cross_examination:
            skipped.append(steps.stage_skipped(CourtStage.CROSS_EXAMINATION, off))
        if not options.judge_questions or options.max_question_rounds == 0:
            skipped.append(steps.stage_skipped(CourtStage.JUDGE_QUESTIONS, off))
        elif court.analyst is None:
            skipped.append(
                steps.stage_skipped(
                    CourtStage.JUDGE_QUESTIONS,
                    "the judge questions arguments the evidence review finds unsupported, "
                    "and the Evidence Agent is disabled",
                )
            )
        if not options.jury:
            skipped.append(steps.stage_skipped(CourtStage.JURY_INDEPENDENT_DELIBERATION, off))
        if not options.jury or not options.deliberation or len(court.jurors) < 2:
            reason = off if options.jury and not options.deliberation else (
                "a single juror has no one to deliberate with" if options.jury else off
            )
            skipped.append(steps.stage_skipped(CourtStage.JURY_DELIBERATION, reason))
        if not options.audit:
            skipped.append(steps.stage_skipped(CourtStage.LEGAL_PROCESS_AUDIT, off))
        return _update(CourtStage.CASE_INITIALIZATION, Step(skipped))

    return node


def _evidence_analysis(court: Court) -> Node:
    def node(state: CourtState) -> Dict[str, Any]:
        analysis, step = steps.evidence_analysis(court)
        return _update(CourtStage.EVIDENCE_ANALYSIS, step, evidence_analysis=analysis)

    return node


def _debate(court: Court, stage: CourtStage) -> Node:
    """Every party that speaks at a debate stage, in speaking order"""

    def node(state: CourtState) -> Dict[str, Any]:
        presented = list(state.get("arguments", []))
        turns: List[AdvocateTurn] = []
        step = Step()
        for role in STAGE_SPEAKERS[stage]:
            turn, turn_step = steps.advocate_turn(
                court,
                stage,
                role,
                presented,
                _context(state),
                f"{role.code}-{STAGE_CODES[stage]}",
                questions=state.get("judge_questions", []),
            )
            turns.append(turn)
            presented.extend(turn.arguments)
            step.events += turn_step.events
            step.messages += turn_step.messages
        new = [a for t in turns for a in t.arguments]
        return _update(stage, step, turns=turns, **_split(new))

    return node


def _evidence_review(court: Court) -> Node:
    """Review every argument not yet reviewed; flag the unsupported for the judge"""

    def node(state: CourtState) -> Dict[str, Any]:
        presented = list(state.get("arguments", []))
        reviewed = set(state.get("reviewed_ids", []))
        under_review = [a for a in presented if a.argument_id not in reviewed]
        rounds = len(state.get("question_rounds", []))
        message_id = "MSG-EVIDENCE-REVIEW" if rounds == 0 else f"MSG-EVIDENCE-REVIEW-ANS{rounds}"

        review, step = steps.evidence_review(
            court,
            presented,
            under_review,
            _context(state),
            message_id,
            questions=state.get("judge_questions", []),
        )
        flagged = review.unsupported_argument_ids
        options = court.options
        asking = options.judge_questions and rounds < options.max_question_rounds
        if rounds == 0 and asking and not flagged:
            step.events.append(
                steps.stage_skipped(
                    CourtStage.JUDGE_QUESTIONS,
                    "the evidence review found no argument unsupported",
                )
            )
        return _update(
            CourtStage.EVIDENCE_REVIEW,
            step,
            evidence_reviews=[review],
            reviewed_ids=[a.argument_id for a in under_review],
            pending_flagged=list(flagged) if asking else [],
        )

    return node


def _judge_questions(court: Court) -> Node:
    def node(state: CourtState) -> Dict[str, Any]:
        round_number = len(state.get("question_rounds", [])) + 1
        question_round, step = steps.judge_questions(
            court,
            state.get("arguments", []),
            state.get("pending_flagged", []),
            round_number,
            _context(state),
            earlier=state.get("judge_questions", []),
        )
        return _update(
            CourtStage.JUDGE_QUESTIONS,
            step,
            question_rounds=[question_round],
            judge_questions=list(question_round.questions),
            pending_flagged=[],
        )

    return node


def _party_answers(court: Court) -> Node:
    """Each party the judge questioned answers, citing the record"""

    def node(state: CourtState) -> Dict[str, Any]:
        latest = state["question_rounds"][-1]
        presented = list(state.get("arguments", []))
        turns: List[AdvocateTurn] = []
        step = Step()
        for role in (AdvocateRole.PROSECUTION, AdvocateRole.DEFENSE):
            if not any(q.addressed_to == role.agent_id for q in latest.questions):
                continue
            turn, turn_step = steps.advocate_turn(
                court,
                ANSWER_STAGE,
                role,
                presented,
                _context(state),
                f"{role.code}-ANS{latest.round}",
                questions=latest.questions,
            )
            turns.append(turn)
            presented.extend(turn.arguments)
            step.events += turn_step.events
            step.messages += turn_step.messages
        new = [a for t in turns for a in t.arguments]
        return _update(CourtStage.JUDGE_QUESTIONS, step, turns=turns, **_split(new))

    return node


def _jury_independent(court: Court) -> Node:
    def node(state: CourtState) -> Dict[str, Any]:
        decisions, step = steps.jury_independent(
            court,
            state.get("arguments", []),
            _context(state),
            questions=state.get("judge_questions", []),
        )
        return _update(
            CourtStage.JURY_INDEPENDENT_DELIBERATION,
            step,
            jury_independent=decisions,
            jury_decisions=[d.verdict for d in decisions],
        )

    return node


def _jury_deliberation(court: Court) -> Node:
    def node(state: CourtState) -> Dict[str, Any]:
        decisions, step = steps.jury_deliberation(
            court,
            state.get("arguments", []),
            _context(state),
            state["jury_independent"],
            questions=state.get("judge_questions", []),
        )
        return _update(
            CourtStage.JURY_DELIBERATION,
            step,
            jury_deliberation=decisions,
            jury_decisions=[d.verdict for d in decisions],
        )

    return node


def _jury_verdict(court: Court) -> Node:
    def node(state: CourtState) -> Dict[str, Any]:
        deliberation = state.get("jury_deliberation", [])
        result, step = steps.jury_verdict(court, state["jury_independent"], deliberation)
        stage = (
            CourtStage.JURY_DELIBERATION
            if deliberation
            else CourtStage.JURY_INDEPENDENT_DELIBERATION
        )
        return _update(stage, step, jury_result=result)

    return node


def _judge_decision(court: Court) -> Node:
    def node(state: CourtState) -> Dict[str, Any]:
        judgment, agreement, step = steps.judge_decision(
            court,
            state.get("arguments", []),
            _context(state),
            state.get("jury_result"),
            questions=state.get("judge_questions", []),
        )
        return _update(
            CourtStage.JUDGE_DECISION,
            step,
            judgment=judgment,
            judge_decision=judgment.verdict,
            judge_jury_agreement=agreement,
        )

    return node


def _legal_process_audit(court: Court) -> Node:
    def node(state: CourtState) -> Dict[str, Any]:
        audit, step = steps.process_audit(court, run_from_state(state))
        return _update(
            CourtStage.LEGAL_PROCESS_AUDIT, step, audit=audit, audit_report=audit.report
        )

    return node


def _case_complete(court: Court) -> Node:
    def node(state: CourtState) -> Dict[str, Any]:
        return _update(CourtStage.CASE_COMPLETE, Step([steps.case_complete(court)]))

    return node


# ============================================================================
# The graph
# ============================================================================

NODES = [
    "case_initialization",
    "evidence_analysis",
    "prosecution_opening",
    "defense_opening",
    "prosecution_argument",
    "defense_argument",
    "cross_examination",
    "evidence_review",
    "judge_questions",
    "party_answers",
    "answer_review",
    "prosecution_rebuttal",
    "defense_rebuttal",
    "closing_arguments",
    "jury_independent_deliberation",
    "jury_deliberation",
    "jury_verdict",
    "judge_decision",
    "legal_process_audit",
    "case_complete",
]


def build_court_graph(court: Court) -> Any:
    """Compile the court procedure for one configured court"""
    options = court.options
    graph = StateGraph(CourtState)

    graph.add_node("case_initialization", _case_initialization(court))
    graph.add_node("evidence_analysis", _evidence_analysis(court))
    for stage in (
        CourtStage.PROSECUTION_OPENING,
        CourtStage.DEFENSE_OPENING,
        CourtStage.PROSECUTION_ARGUMENT,
        CourtStage.DEFENSE_ARGUMENT,
        CourtStage.CROSS_EXAMINATION,
        CourtStage.PROSECUTION_REBUTTAL,
        CourtStage.DEFENSE_REBUTTAL,
        CourtStage.CLOSING_ARGUMENTS,
    ):
        graph.add_node(stage.value.lower(), _debate(court, stage))
    graph.add_node("evidence_review", _evidence_review(court))
    graph.add_node("judge_questions", _judge_questions(court))
    graph.add_node("party_answers", _party_answers(court))
    graph.add_node("answer_review", _evidence_review(court))
    graph.add_node("jury_independent_deliberation", _jury_independent(court))
    graph.add_node("jury_deliberation", _jury_deliberation(court))
    graph.add_node("jury_verdict", _jury_verdict(court))
    graph.add_node("judge_decision", _judge_decision(court))
    graph.add_node("legal_process_audit", _legal_process_audit(court))
    graph.add_node("case_complete", _case_complete(court))

    has_evidence = court.analyst is not None
    has_jury = options.jury and bool(court.jurors)
    deliberates = has_jury and options.deliberation and len(court.jurors) > 1

    def after_initialization(state: CourtState) -> str:
        return "evidence_analysis" if has_evidence else "prosecution_opening"

    def after_arguments(state: CourtState) -> str:
        if options.cross_examination:
            return "cross_examination"
        return after_cross_examination(state)

    def after_cross_examination(state: CourtState) -> str:
        return "evidence_review" if has_evidence else "prosecution_rebuttal"

    def after_review(state: CourtState) -> str:
        # The judge requests more when an argument lacks evidence.
        return "judge_questions" if state.get("pending_flagged") else "prosecution_rebuttal"

    def after_closing(state: CourtState) -> str:
        return "jury_independent_deliberation" if has_jury else "judge_decision"

    def after_independent(state: CourtState) -> str:
        return "jury_deliberation" if deliberates else "jury_verdict"

    def after_decision(state: CourtState) -> str:
        return "legal_process_audit" if options.audit else "case_complete"

    graph.add_edge(START, "case_initialization")
    graph.add_conditional_edges(
        "case_initialization",
        after_initialization,
        ["evidence_analysis", "prosecution_opening"],
    )
    graph.add_edge("evidence_analysis", "prosecution_opening")
    graph.add_edge("prosecution_opening", "defense_opening")
    graph.add_edge("defense_opening", "prosecution_argument")
    graph.add_edge("prosecution_argument", "defense_argument")
    graph.add_conditional_edges(
        "defense_argument",
        after_arguments,
        ["cross_examination", "evidence_review", "prosecution_rebuttal"],
    )
    graph.add_conditional_edges(
        "cross_examination",
        after_cross_examination,
        ["evidence_review", "prosecution_rebuttal"],
    )
    graph.add_conditional_edges(
        "evidence_review", after_review, ["judge_questions", "prosecution_rebuttal"]
    )
    graph.add_edge("judge_questions", "party_answers")
    graph.add_edge("party_answers", "answer_review")
    graph.add_conditional_edges(
        "answer_review", after_review, ["judge_questions", "prosecution_rebuttal"]
    )
    graph.add_edge("prosecution_rebuttal", "defense_rebuttal")
    graph.add_edge("defense_rebuttal", "closing_arguments")
    graph.add_conditional_edges(
        "closing_arguments",
        after_closing,
        ["jury_independent_deliberation", "judge_decision"],
    )
    graph.add_conditional_edges(
        "jury_independent_deliberation",
        after_independent,
        ["jury_deliberation", "jury_verdict"],
    )
    graph.add_edge("jury_deliberation", "jury_verdict")
    graph.add_edge("jury_verdict", "judge_decision")
    graph.add_conditional_edges(
        "judge_decision", after_decision, ["legal_process_audit", "case_complete"]
    )
    graph.add_edge("legal_process_audit", "case_complete")
    graph.add_edge("case_complete", END)
    return graph.compile()


def initial_state(court: Court) -> CourtState:
    """The state a trial starts from: the case record, evaluated"""
    return CourtState(
        case=court.case,
        current_stage=CourtStage.CASE_INITIALIZATION.value,
        facts=list(court.case.facts),
        evidence=list(court.case.evidence),
        applicable_laws=[
            rule
            for rule_id in court.case.applicable_laws
            if (rule := court.registry.get(rule_id)) is not None
        ],
        evaluation=court.evaluation,
        event_history=list(court.opening_events),
        pending_flagged=[],
    )


def run_court(
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
    evidence: bool = True,
    cross_examination: bool = True,
    judge_questions: bool = True,
    max_question_rounds: int = 1,
    jury: bool = True,
    jurors: int = 3,
    deliberation: bool = True,
    jury_rule: JuryRule = JuryRule.UNANIMOUS,
    audit: bool = True,
    audit_agent: bool = True,
    log: Optional[InteractionLog] = None,
    max_attempts: int = 3,
    strict_engine_alignment: bool = False,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> TrialRun:
    """Run the full spec section 14 procedure for one seeded case

    ``on_event`` is called with every event as the court produces it - the
    hook for live progress and, later, streaming to the frontend.
    """
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
        options=CourtOptions(
            evidence=evidence,
            cross_examination=cross_examination,
            judge_questions=judge_questions,
            max_question_rounds=max_question_rounds,
            jury=jury,
            jurors=jurors,
            deliberation=deliberation,
            jury_rule=jury_rule,
            audit=audit,
            audit_agent=audit_agent,
            max_attempts=max_attempts,
            strict_engine_alignment=strict_engine_alignment,
        ),
    )
    start = initial_state(court)
    if on_event is not None:
        for opening in start["event_history"]:
            on_event(opening)

    final: Dict[str, Any] = dict(start)
    app = build_court_graph(court)
    for mode, chunk in app.stream(
        start,
        stream_mode=["updates", "values"],
        config={"recursion_limit": RECURSION_LIMIT},
    ):
        if mode == "values":
            final = chunk
        elif on_event is not None:
            for update in chunk.values():
                for item in (update or {}).get("event_history", []):
                    on_event(item)
    return run_from_state(final)  # type: ignore[arg-type]


def court_graph_mermaid() -> str:
    """The court procedure as a Mermaid diagram (every branch shown)"""

    class _Placeholder:
        """Enough of a Court to lay the graph out; nothing is ever run"""

        options = CourtOptions()
        analyst = object()
        jurors = [object(), object()]

    return build_court_graph(_Placeholder()).get_graph().draw_mermaid()  # type: ignore[arg-type]
