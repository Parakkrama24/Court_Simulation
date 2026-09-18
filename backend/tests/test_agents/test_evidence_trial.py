"""Integration tests: the Evidence Agent inside the trial, and its CLI

Pinned to ``jury=False``; the jury is covered in ``test_jury_trial.py``.
"""

import json

import pytest

from app.agents.evidence import EvidenceAgentError
from app.cli import main
from app.domain import CourtStage, MessageType
from app.llm import InteractionLog, ScriptedProvider
from app.workflow import (
    DEFAULT_DEBATE_STAGES,
    QUICK_DEBATE_STAGES,
    WorkflowError,
    check_stages,
    run_adversarial_trial,
    run_evidence_analysis,
)

from .conftest import VALID_ANALYSIS, defense_turn, prosecution_turn, review_for

FIRST_EIGHT = [
    "PR-OPEN-1", "PR-OPEN-2", "DF-OPEN-1", "DF-OPEN-2",
    "PR-ARG-1", "PR-ARG-2", "DF-ARG-1", "DF-ARG-2",
]


def record_of(prompt: str) -> dict:
    return json.loads(prompt.split("<case_record>\n")[1].split("\n</case_record>")[0])


def judge_step(decision_with, considered):
    return decision_with(lambda d: d.__setitem__("arguments_considered", list(considered)))


@pytest.fixture
def trial(decision_with):
    review = review_for(FIRST_EIGHT)
    review["reviews"][1].update(support="unsupported", issues=["F004 presented as settled"])
    providers = {
        "evidence": ScriptedProvider([VALID_ANALYSIS, review]),
        "prosecution": ScriptedProvider(
            [
                prosecution_turn(),
                prosecution_turn(["DF-OPEN-1"]),
                prosecution_turn(["DF-ARG-1"]),
                prosecution_turn(),
            ]
        ),
        "defense": ScriptedProvider(
            [
                defense_turn(["PR-OPEN-1"]),
                defense_turn(["PR-ARG-2"]),
                defense_turn(["PR-REB-1"]),
                defense_turn(),
            ]
        ),
        "judge": ScriptedProvider([judge_step(decision_with, ["PR-ARG-1", "DF-ARG-2"])]),
    }
    log = InteractionLog()
    run = run_adversarial_trial(
        "CASE_001",
        prosecution_provider=providers["prosecution"],
        defense_provider=providers["defense"],
        judge_provider=providers["judge"],
        evidence_provider=providers["evidence"],
        log=log,
        jury=False,
    )
    return run, providers, log


class TestEvidenceInTheTrial:
    def test_default_plan_places_review_where_the_spec_does(self):
        assert DEFAULT_DEBATE_STAGES.index(CourtStage.EVIDENCE_REVIEW) == (
            DEFAULT_DEBATE_STAGES.index(CourtStage.DEFENSE_ARGUMENT) + 1
        )

    def test_analysis_runs_before_anyone_argues(self, trial):
        run = trial[0]
        kinds = [(e["stage"], e["event_type"]) for e in run.event_history]
        assert kinds[2:4] == [
            ("EVIDENCE_ANALYSIS", "AGENT_STARTED"),
            ("EVIDENCE_ANALYSIS", "EVIDENCE_ANALYZED"),
        ]
        analyzed = run.event_history[3]
        assert analyzed["claims"] == {"established": 2, "disputed": 1, "unsupported": 1}
        assert analyzed["missing_evidence"] == 1

    def test_review_follows_the_parties_arguments(self, trial):
        run = trial[0]
        stages = [e["stage"] for e in run.event_history if e["event_type"] != "AGENT_STARTED"]
        review_at = stages.index("EVIDENCE_REVIEW")
        assert stages[review_at - 1] == "DEFENSE_ARGUMENT"
        assert stages[review_at + 1] == "PROSECUTION_REBUTTAL"

    def test_review_covers_every_argument_so_far(self, trial):
        run = trial[0]
        reviewed = next(e for e in run.event_history if e["event_type"] == "EVIDENCE_REVIEWED")
        assert reviewed["reviewed"] == FIRST_EIGHT
        assert reviewed["unsupported"] == ["PR-OPEN-2"]
        assert run.evidence_reviews[0].unsupported_argument_ids == ["PR-OPEN-2"]

    def test_advocates_see_the_analysis_from_the_start(self, trial):
        providers = trial[1]
        opening = record_of(providers["prosecution"].requests[0].messages[0].content)
        assert opening["evidence_analysis"]["summary"] == VALID_ANALYSIS["summary"]
        assert opening["evidence_analysis"]["argument_reviews"] == []

    def test_advocates_see_reviews_after_the_review(self, trial):
        providers = trial[1]
        rebuttal = record_of(providers["prosecution"].requests[2].messages[0].content)
        reviews = rebuttal["evidence_analysis"]["argument_reviews"]
        assert len(reviews) == 8
        assert reviews[1] == {
            "argument_id": "PR-OPEN-2",
            "support": "unsupported",
            "issues": ["F004 presented as settled"],
            "reasoning": "Checked against the cited record.",
        }

    def test_review_sees_its_own_analysis(self, trial):
        providers = trial[1]
        review_record = record_of(providers["evidence"].requests[1].messages[0].content)
        assert review_record["evidence_analysis"]["summary"] == VALID_ANALYSIS["summary"]
        assert len(review_record["party_arguments"]) == 8

    def test_judge_sees_analysis_and_reviews(self, trial):
        providers = trial[1]
        record = record_of(providers["judge"].requests[0].messages[0].content)
        assert len(record["evidence_analysis"]["claims"]) == 4
        assert len(record["evidence_analysis"]["argument_reviews"]) == 8
        assert "evidence_analysis" in providers["judge"].requests[0].system

    def test_messages_include_the_evidence_agent(self, trial):
        run = trial[0]
        types = [m.message_type for m in run.messages]
        assert types[0] == MessageType.EVIDENCE_ANALYSIS
        assert types[5] == MessageType.EVIDENCE_REVIEW
        assert types[-1] == MessageType.DECISION
        assert len(run.messages) == 11

    def test_every_call_is_logged_and_counted(self, trial):
        run, _, log = trial
        assert [r.agent_id for r in log.records].count("evidence_agent") == 2
        assert len(log.records) == 11
        evidence_tokens = run.evidence_analysis.usage.output_tokens
        assert run.usage.output_tokens > run.judgment.usage.output_tokens + evidence_tokens

    def test_run_serialises(self, trial):
        data = json.loads(trial[0].model_dump_json())
        assert data["evidence_analysis"]["output"]["summary"] == VALID_ANALYSIS["summary"]
        assert len(data["evidence_reviews"]) == 1


class TestEvidenceTrialVariants:
    def test_quick_trial_analyses_but_does_not_review(self, decision_with):
        steps = [
            VALID_ANALYSIS,
            prosecution_turn(),
            defense_turn(),
            prosecution_turn(),
            defense_turn(),
            judge_step(decision_with, ["PR-OPEN-1", "DF-OPEN-1"]),
        ]
        run = run_adversarial_trial(
            "CASE_001", ScriptedProvider(steps), stages=QUICK_DEBATE_STAGES, jury=False
        )
        assert run.evidence_analysis is not None
        assert run.evidence_reviews == []

    def test_second_review_covers_only_new_arguments(self, decision_with):
        stages = [
            CourtStage.PROSECUTION_OPENING,
            CourtStage.DEFENSE_OPENING,
            CourtStage.EVIDENCE_REVIEW,
            CourtStage.CLOSING_ARGUMENTS,
            CourtStage.EVIDENCE_REVIEW,
        ]
        steps = [
            VALID_ANALYSIS,
            prosecution_turn(),
            defense_turn(),
            review_for(["PR-OPEN-1", "PR-OPEN-2", "DF-OPEN-1", "DF-OPEN-2"]),
            prosecution_turn(),
            defense_turn(),
            review_for(["PR-CLOSE-1", "PR-CLOSE-2", "DF-CLOSE-1", "DF-CLOSE-2"]),
            judge_step(decision_with, ["PR-OPEN-1", "DF-OPEN-1"]),
        ]
        run = run_adversarial_trial(
            "CASE_001", ScriptedProvider(steps), stages=stages, jury=False
        )
        assert [r.message.message_id for r in run.evidence_reviews] == [
            "MSG-EVIDENCE-REVIEW",
            "MSG-EVIDENCE-REVIEW2",
        ]
        assert run.evidence_reviews[1].message.argument_ids[0] == "PR-CLOSE-1"

    def test_disabling_evidence_drops_it_from_the_default_plan(self, decision_with):
        steps = [
            prosecution_turn(),
            defense_turn(),
            prosecution_turn(["DF-OPEN-1"]),
            defense_turn(),
            prosecution_turn(["DF-ARG-1"]),
            defense_turn(["PR-REB-1"]),
            prosecution_turn(),
            defense_turn(),
            judge_step(decision_with, ["PR-OPEN-1", "DF-OPEN-1"]),
        ]
        run = run_adversarial_trial(
            "CASE_001", ScriptedProvider(steps), evidence=False, jury=False
        )
        assert run.evidence_analysis is None
        assert all(m.message_type != MessageType.EVIDENCE_REVIEW for m in run.messages)

    def test_evidence_agent_failure_stops_the_trial(self):
        with pytest.raises(EvidenceAgentError):
            run_adversarial_trial("CASE_001", ScriptedProvider(["bad"] * 3))

    def test_missing_evidence_provider(self):
        with pytest.raises(WorkflowError, match="missing: evidence"):
            run_adversarial_trial(
                "CASE_001",
                prosecution_provider=ScriptedProvider([]),
                defense_provider=ScriptedProvider([]),
                judge_provider=ScriptedProvider([]),
            )


class TestEvidenceStagePlan:
    def test_default_plan_is_valid(self):
        check_stages(DEFAULT_DEBATE_STAGES)

    def test_review_needs_the_evidence_agent(self):
        with pytest.raises(WorkflowError, match="needs the Evidence Agent"):
            check_stages(DEFAULT_DEBATE_STAGES, evidence_enabled=False)

    def test_review_needs_arguments_first(self):
        with pytest.raises(WorkflowError, match="at least one argument"):
            check_stages([CourtStage.EVIDENCE_REVIEW, CourtStage.PROSECUTION_OPENING])

    def test_back_to_back_reviews(self):
        with pytest.raises(WorkflowError, match="since the last review"):
            check_stages(
                [
                    CourtStage.PROSECUTION_OPENING,
                    CourtStage.EVIDENCE_REVIEW,
                    CourtStage.EVIDENCE_REVIEW,
                ]
            )


class TestEvidenceOnlyWorkflow:
    def test_single_call(self, valid_analysis):
        provider = ScriptedProvider([valid_analysis])
        run = run_evidence_analysis("CASE_001", provider)
        assert len(provider.requests) == 1
        assert [e["event_type"] for e in run.event_history][-1] == "EVIDENCE_ANALYZED"
        assert len(run.analysis.provenance) == 8

    def test_unknown_case(self):
        with pytest.raises(WorkflowError, match="Unknown case"):
            run_evidence_analysis("CASE_404", ScriptedProvider([]))


class TestEvidenceCli:
    def test_show_prompt(self, capsys):
        assert main(["evidence", "CASE_001", "--show-prompt"]) == 0
        out = capsys.readouterr().out
        assert "court's evidence analyst" in out
        assert "Task: EVIDENCE_ANALYSIS" in out

    def test_evidence_command(self, monkeypatch, capsys, tmp_path, valid_analysis):
        monkeypatch.setattr(
            "app.cli._build_provider", lambda args, settings: ScriptedProvider([valid_analysis])
        )
        assert main(["evidence", "CASE_001", "--log-file", str(tmp_path / "e.jsonl")]) == 0
        out = capsys.readouterr().out
        assert "[EVIDENCE_ANALYSIS] evidence_agent" in out
        assert "[disputed   ] Alex physically attacked David." in out
        assert "for: E006, W001   against: E007, W003" in out
        assert "W003 low" in out
        assert "LAW_104.C2" in out
        assert "E005: no record of who collected or produced it" in out

    def test_trial_prints_the_evidence_stages(self, monkeypatch, capsys, tmp_path, decision_with):
        steps = [
            VALID_ANALYSIS,
            prosecution_turn(),
            defense_turn(),
            prosecution_turn(),
            defense_turn(),
            judge_step(decision_with, ["PR-OPEN-1", "DF-OPEN-1"]),
        ]
        monkeypatch.setattr(
            "app.cli._build_provider", lambda args, settings: ScriptedProvider(steps)
        )
        log_file = str(tmp_path / "t.jsonl")
        code = main(["trial", "CASE_001", "--quick", "--no-jury", "--log-file", log_file])
        assert code == 0
        out = capsys.readouterr().out
        assert out.index("[EVIDENCE_ANALYSIS]") < out.index("[PROSECUTION_OPENING]")
