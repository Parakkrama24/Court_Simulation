"""Integration tests: the full court procedure as a LangGraph state machine"""

import copy
import json

import pytest

from app.cli import main
from app.domain import AuditReport, CourtStage, LegalRule, Verdict
from app.llm import InteractionLog, ScriptedProvider
from app.workflow import (
    TrialRun,
    WorkflowError,
    build_court_graph,
    court_graph_mermaid,
    deterministic_findings,
    initial_state,
    open_court,
    run_adversarial_trial,
    run_court,
)
from app.workflow.graph import RECURSION_LIMIT
from app.workflow.steps import CourtOptions

from .conftest import (
    VALID_ANALYSIS,
    VALID_DECISION,
    auditor_output,
    cross_turn,
    defense_turn,
    juror_verdict,
    prosecution_turn,
    questions_output,
    review_for,
)

BOTH = ["PR-OPEN-1", "DF-OPEN-1"]
FIRST_TWELVE = [
    "PR-OPEN-1", "PR-OPEN-2", "DF-OPEN-1", "DF-OPEN-2",
    "PR-ARG-1", "PR-ARG-2", "DF-ARG-1", "DF-ARG-2",
    "PR-CROSS-1", "PR-CROSS-2", "DF-CROSS-1", "DF-CROSS-2",
]
SPEC_ORDER = [
    "CASE_INITIALIZATION",
    "RULE_EVALUATION",
    "EVIDENCE_ANALYSIS",
    "PROSECUTION_OPENING",
    "DEFENSE_OPENING",
    "PROSECUTION_ARGUMENT",
    "DEFENSE_ARGUMENT",
    "CROSS_EXAMINATION",
    "EVIDENCE_REVIEW",
    "JUDGE_QUESTIONS",
    "EVIDENCE_REVIEW",  # the review of the answers
    "PROSECUTION_REBUTTAL",
    "DEFENSE_REBUTTAL",
    "CLOSING_ARGUMENTS",
    "JURY_INDEPENDENT_DELIBERATION",
    "JURY_DELIBERATION",
    "JUDGE_DECISION",
    "LEGAL_PROCESS_AUDIT",
    "CASE_COMPLETE",
]


def decision():
    data = copy.deepcopy(VALID_DECISION)
    data["arguments_considered"] = list(BOTH)
    return data


def review(ids, unsupported=()):
    data = review_for(ids)
    for item in data["reviews"]:
        if item["argument_id"] in unsupported:
            item.update(support="unsupported", issues=["not supported by what it cites"])
    return data


def debate(unsupported=("PR-OPEN-2",), cross=True):
    """Analysis, openings, arguments, cross-examination, and the first review"""
    steps = [
        VALID_ANALYSIS,
        prosecution_turn(), defense_turn(),
        prosecution_turn(), defense_turn(),
    ]
    ids = FIRST_TWELVE[:8]
    if cross:
        steps += [cross_turn(prosecution_turn(), "W003"), cross_turn(defense_turn(), "W001")]
        ids = FIRST_TWELVE
    return steps + [review(ids, unsupported)]


def ending(jurors=3, deliberation=True, audit_agent=True):
    """Rebuttals, closings, the jury, the judgment, and the audit"""
    steps = [
        prosecution_turn(["DF-ARG-1"]), defense_turn(["PR-REB-1"]),
        prosecution_turn(), defense_turn(),
        *[juror_verdict(considered=BOTH)] * jurors,
    ]
    if deliberation and jurors > 1:
        steps += [juror_verdict(considered=BOTH, deliberation=True)] * jurors
    steps.append(decision())
    if audit_agent:
        steps.append(auditor_output(findings=[]))
    return steps


def one_question_round(answer_unsupported=()):
    return [
        questions_output(("prosecution", ["PR-OPEN-2"])),
        prosecution_turn(["JQ1-1"]),
        review(["PR-ANS1-1", "PR-ANS1-2"], answer_unsupported),
    ]


def stages_of(run):
    """Stage transitions, in order, excluding skipped stages"""
    order = []
    for entry in run.event_history:
        if entry["event_type"] == "STAGE_SKIPPED":
            continue
        if not order or order[-1] != entry["stage"]:
            order.append(entry["stage"])
    return order


def skipped(run):
    return {
        e["stage"]: e["reason"] for e in run.event_history if e["event_type"] == "STAGE_SKIPPED"
    }


@pytest.fixture
def full_run():
    provider = ScriptedProvider(debate() + one_question_round() + ending())
    log = InteractionLog()
    events = []
    run = run_court("CASE_001", provider, log=log, on_event=events.append)
    return run, provider, log, events


# ============================================================================
# The full procedure
# ============================================================================


class TestFullProcedure:
    def test_follows_the_spec_order(self, full_run):
        run, provider, _, _ = full_run
        assert provider.remaining == 0
        assert stages_of(run) == SPEC_ORDER

    def test_every_spec_stage_ran(self, full_run):
        ran = set(stages_of(full_run[0]))
        assert {stage.value for stage in CourtStage} <= ran
        assert skipped(full_run[0]) == {}

    def test_cross_examination_turns(self, full_run):
        run = full_run[0]
        cross = [t for t in run.turns if t.stage == CourtStage.CROSS_EXAMINATION]
        assert [t.agent_id for t in cross] == ["prosecution_agent", "defense_agent"]
        assert cross[0].arguments[0].argument_id == "PR-CROSS-1"
        assert cross[0].arguments[0].witness_ids == ["W003"]

    def test_the_judge_requests_more_when_an_argument_lacks_evidence(self, full_run):
        run = full_run[0]
        [question] = run.judge_questions
        assert question.question_id == "JQ1-1"
        assert question.addressed_to == "prosecution_agent"
        assert question.argument_ids == ["PR-OPEN-2"]
        assert run.judge_question_rounds[0].flagged_argument_ids == ["PR-OPEN-2"]

    def test_the_party_answers_and_the_answers_are_reviewed(self, full_run):
        run = full_run[0]
        answer = next(t for t in run.turns if t.stage == CourtStage.JUDGE_QUESTIONS)
        assert [a.argument_id for a in answer.arguments] == ["PR-ANS1-1", "PR-ANS1-2"]
        assert answer.arguments[0].counter_argument_ids == ["JQ1-1"]
        response = next(e for e in run.event_history if e["event_type"] == "AGENT_RESPONSE")
        assert response["answered"] == ["JQ1-1"]
        second_review = run.evidence_reviews[1]
        assert second_review.message.message_id == "MSG-EVIDENCE-REVIEW-ANS1"
        assert [r.argument_id for r in second_review.output.reviews] == ["PR-ANS1-1", "PR-ANS1-2"]

    def test_later_speakers_see_the_questions_and_answers(self, full_run):
        provider = full_run[1]
        rebuttal = next(
            r for r in provider.requests if "Stage: PROSECUTION_REBUTTAL" in r.messages[0].content
        )
        record = json.loads(
            rebuttal.messages[0].content.split("<case_record>\n")[1].split("\n</case_record>")[0]
        )
        assert record["judge_questions"][0]["question_id"] == "JQ1-1"
        assert "PR-ANS1-1" in [a["argument_id"] for a in record["party_arguments"]]

    def test_jurors_and_judge_see_the_questions(self, full_run):
        provider = full_run[1]

        def record_for(stage_marker):
            prompts = [
                r.messages[0].content
                for r in provider.requests
                if stage_marker in r.messages[0].content
            ]
            return prompts, [
                json.loads(p.split("<case_record>\n")[1].split("\n</case_record>")[0])
                for p in prompts
            ]

        juror_prompts, juror_records = record_for("Stage: JURY_INDEPENDENT_DELIBERATION")
        assert len(juror_prompts) == 3
        assert juror_prompts[0] == juror_prompts[1] == juror_prompts[2]  # still independent
        assert juror_records[0]["judge_questions"][0]["question_id"] == "JQ1-1"
        _, judge_records = record_for("Decide each charge against the defendant")
        assert judge_records[0]["judge_questions"][0]["question_id"] == "JQ1-1"
        _, review_records = record_for("Review each of these arguments exactly once: PR-ANS1-1")
        assert review_records[0]["judge_questions"][0]["question_id"] == "JQ1-1"

    def test_the_audit_is_accurate(self, full_run):
        run = full_run[0]
        checks = [f.check for f in run.audit.findings]
        assert "accepted_with_invalid_reference" not in checks  # answers cite JQ1-1
        assert "unsupported_argument" in checks
        assert run.audit_report.metadata["overall_status"] == "minor_issues"

    def test_every_event_is_streamed_once_in_order(self, full_run):
        run, _, _, events = full_run
        assert events == run.event_history

    def test_every_call_is_logged(self, full_run):
        log = full_run[2]
        agents = [r.agent_id for r in log.records]
        assert agents.count("judge_agent") == 2  # questions, then the decision
        assert len(log.records) == 23

    def test_the_run_serialises_and_audits_identically(self, full_run):
        run = full_run[0]
        reloaded = TrialRun.model_validate_json(run.model_dump_json())
        assert len(reloaded.judge_questions) == 1
        assert [f.model_dump() for f in deterministic_findings(reloaded)] == [
            f.model_dump() for f in deterministic_findings(run)
        ]


# ============================================================================
# The state spec section 17 asks for
# ============================================================================


class TestCourtState:
    def test_final_state_has_every_spec_field(self):
        steps = debate() + one_question_round() + ending()
        court = open_court("CASE_001", ScriptedProvider(steps))
        app = build_court_graph(court)
        state = app.invoke(initial_state(court), config={"recursion_limit": RECURSION_LIMIT})

        assert state["case"].case_id == "CASE_001"
        assert state["current_stage"] == "CASE_COMPLETE"
        assert len(state["facts"]) == 8 and len(state["evidence"]) == 8
        assert all(isinstance(rule, LegalRule) for rule in state["applicable_laws"])
        assert [r.rule_id for r in state["applicable_laws"]] == court.case.applicable_laws
        assert all(a.agent_id == "prosecution_agent" for a in state["prosecution_arguments"])
        assert all(a.agent_id == "defense_agent" for a in state["defense_arguments"])
        assert len(state["prosecution_arguments"]) + len(state["defense_arguments"]) == len(
            state["arguments"]
        )
        assert state["evidence_analysis"].output.summary == VALID_ANALYSIS["summary"]
        assert [q.question_id for q in state["judge_questions"]] == ["JQ1-1"]
        assert len(state["jury_decisions"]) == 6
        assert isinstance(state["judge_decision"], Verdict)
        assert isinstance(state["audit_report"], AuditReport)
        assert state["event_history"][-1]["event_type"] == "CASE_COMPLETE"


# ============================================================================
# Conditional transitions
# ============================================================================


class TestConditionalTransitions:
    def test_no_questions_when_nothing_is_unsupported(self):
        provider = ScriptedProvider(debate(unsupported=()) + ending())
        run = run_court("CASE_001", provider)
        assert provider.remaining == 0
        assert run.judge_questions == []
        assert "JUDGE_QUESTIONS" not in stages_of(run)
        assert skipped(run) == {
            "JUDGE_QUESTIONS": "the evidence review found no argument unsupported"
        }
        not_required = [f for f in run.audit.findings if f.check == "stage_not_required"]
        assert [f.stage for f in not_required] == ["JUDGE_QUESTIONS"]

    def test_questioning_repeats_while_answers_stay_unsupported(self):
        second_round = [
            questions_output(("prosecution", ["PR-ANS1-1"])),
            prosecution_turn(["JQ2-1"]),
            review(["PR-ANS2-1", "PR-ANS2-2"]),
        ]
        steps = (
            debate()
            + one_question_round(answer_unsupported=("PR-ANS1-1",))
            + second_round
            + ending()
        )
        provider = ScriptedProvider(steps)
        run = run_court("CASE_001", provider, max_question_rounds=2)
        assert provider.remaining == 0
        assert [q.question_id for q in run.judge_questions] == ["JQ1-1", "JQ2-1"]
        assert run.judge_question_rounds[1].flagged_argument_ids == ["PR-ANS1-1"]

    def test_questioning_stops_at_the_round_limit(self):
        steps = debate() + one_question_round(answer_unsupported=("PR-ANS1-1",)) + ending()
        provider = ScriptedProvider(steps)
        run = run_court("CASE_001", provider, max_question_rounds=1)
        assert provider.remaining == 0
        assert len(run.judge_question_rounds) == 1
        assert stages_of(run)[stages_of(run).index("JUDGE_QUESTIONS") + 2] == (
            "PROSECUTION_REBUTTAL"
        )

    def test_questions_can_be_turned_off(self):
        provider = ScriptedProvider(debate() + ending())
        run = run_court("CASE_001", provider, judge_questions=False)
        assert provider.remaining == 0
        assert run.judge_questions == []
        assert "disabled" in skipped(run)["JUDGE_QUESTIONS"]

    def test_without_cross_examination(self):
        provider = ScriptedProvider(debate(cross=False) + one_question_round() + ending())
        run = run_court("CASE_001", provider, cross_examination=False)
        assert provider.remaining == 0
        assert "CROSS_EXAMINATION" not in stages_of(run)
        assert "disabled" in skipped(run)["CROSS_EXAMINATION"]

    def test_without_the_evidence_agent(self):
        steps = [prosecution_turn(), defense_turn(), prosecution_turn(), defense_turn(),
                 cross_turn(prosecution_turn(), "W003"), cross_turn(defense_turn(), "W001")]
        provider = ScriptedProvider(steps + ending())
        run = run_court("CASE_001", provider, evidence=False)
        assert provider.remaining == 0
        reasons = skipped(run)
        assert {"EVIDENCE_ANALYSIS", "EVIDENCE_REVIEW", "JUDGE_QUESTIONS"} <= set(reasons)
        assert "Evidence Agent is disabled" in reasons["JUDGE_QUESTIONS"]
        assert stages_of(run)[2] == "PROSECUTION_OPENING"

    def test_without_jury_or_audit(self):
        steps = debate() + one_question_round() + ending(jurors=0, audit_agent=False)
        provider = ScriptedProvider(steps)
        run = run_court("CASE_001", provider, jury=False, audit=False)
        assert provider.remaining == 0
        order = stages_of(run)
        assert order[-3:] == ["CLOSING_ARGUMENTS", "JUDGE_DECISION", "CASE_COMPLETE"]
        assert run.jury_result is None and run.audit is None
        assert {"JURY_INDEPENDENT_DELIBERATION", "JURY_DELIBERATION", "LEGAL_PROCESS_AUDIT"} <= (
            set(skipped(run))
        )

    def test_a_single_juror_does_not_deliberate(self):
        steps = debate() + one_question_round() + ending(jurors=1)
        provider = ScriptedProvider(steps)
        run = run_court("CASE_001", provider, jurors=1)
        assert provider.remaining == 0
        assert run.jury_deliberation == []
        assert skipped(run)["JURY_DELIBERATION"] == "a single juror has no one to deliberate with"

    def test_deterministic_audit_makes_no_auditor_call(self):
        steps = debate() + one_question_round() + ending(audit_agent=False)
        provider = ScriptedProvider(steps)
        run = run_court("CASE_001", provider, audit_agent=False)
        assert provider.remaining == 0
        assert run.audit.auditor is None


class TestConfiguration:
    def test_problems_are_raised_before_any_model_call(self):
        provider = ScriptedProvider([])
        with pytest.raises(WorkflowError, match="max_question_rounds"):
            run_court("CASE_001", provider, max_question_rounds=-1)
        with pytest.raises(WorkflowError, match="between 1 and 12"):
            run_court("CASE_001", provider, jurors=0)
        with pytest.raises(WorkflowError, match="Unknown case"):
            run_court("CASE_404", provider)
        assert provider.requests == []

    def test_open_court_seats_the_agents(self):
        court = open_court(
            "CASE_001", ScriptedProvider([]), options=CourtOptions(jurors=5, evidence=False)
        )
        assert court.analyst is None
        assert [j.juror_id for j in court.jurors] == [f"jury_{i}" for i in range(1, 6)]
        assert [e["event_type"] for e in court.opening_events] == [
            "CASE_LOADED",
            "RULES_EVALUATED",
        ]

    def test_the_linear_runner_can_now_cross_examine(self, decision_with):
        stages = [
            CourtStage.PROSECUTION_OPENING,
            CourtStage.DEFENSE_OPENING,
            CourtStage.CROSS_EXAMINATION,
        ]
        steps = [
            prosecution_turn(),
            defense_turn(),
            cross_turn(prosecution_turn(), "W003"),
            cross_turn(defense_turn(), "W001"),
            decision(),
        ]
        run = run_adversarial_trial(
            "CASE_001", ScriptedProvider(steps), stages=stages, evidence=False, jury=False,
            audit=False,
        )
        assert run.turns[-1].arguments[0].argument_id == "DF-CROSS-1"


class TestGraphDiagram:
    def test_mermaid_shows_every_branch(self):
        diagram = court_graph_mermaid()
        for edge in (
            "evidence_review -.-> judge_questions",
            "answer_review -.-> judge_questions",
            "judge_questions --> party_answers",
            "closing_arguments -.-> jury_independent_deliberation",
            "judge_decision -.-> legal_process_audit",
        ):
            assert edge in diagram


# ============================================================================
# CLI
# ============================================================================


class TestCourtCli:
    def _patch(self, monkeypatch, steps):
        monkeypatch.setattr(
            "app.cli._build_provider", lambda args, settings: ScriptedProvider(steps)
        )

    def test_show_graph(self, capsys):
        assert main(["court", "CASE_001", "--show-graph"]) == 0
        out = capsys.readouterr().out
        assert "graph TD" in out and "judge_questions" in out

    def test_court_transcript(self, monkeypatch, capsys, tmp_path):
        self._patch(monkeypatch, debate() + one_question_round() + ending())
        assert main(["court", "CASE_001", "--log-file", str(tmp_path / "c.jsonl")]) == 0
        out = capsys.readouterr().out
        assert "[CROSS_EXAMINATION] prosecution_agent" in out
        assert "[JUDGE_QUESTIONS] judge_agent, round 1" in out
        assert "flagged as unsupported: PR-OPEN-2" in out
        assert "JQ1-1 -> prosecution_agent (about PR-OPEN-2)" in out
        assert "PR-ANS1-1:" in out and "(answers JQ1-1)" in out
        assert out.index("[JUDGE_QUESTIONS]") < out.index("[PROSECUTION_REBUTTAL]")
        assert "[LEGAL_PROCESS_AUDIT]" in out

    def test_live_events(self, monkeypatch, capsys, tmp_path):
        self._patch(monkeypatch, debate() + one_question_round() + ending())
        args = ["court", "CASE_001", "--events", "--log-file", str(tmp_path / "c.jsonl")]
        assert main(args) == 0
        out = capsys.readouterr().out
        assert "CASE_001: the court is in session" in out
        assert "JUDGE_QUESTIONS                JUDGE_QUESTION" in out
        assert "JUDGE_QUESTIONS                AGENT_RESPONSE" in out
        assert out.index("AGENT_RESPONSE") < out.index("[EVIDENCE_ANALYSIS]")
