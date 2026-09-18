"""Integration tests: Prosecution <-> Defense -> Judge, and the trial CLI

These pin the Phase 4 trial (``evidence=False, jury=False``); the Evidence Agent's part of
the trial is covered in ``test_evidence_trial.py``.
"""

import json

import pytest

from app.cli import main
from app.domain import CourtStage, MessageType
from app.llm import InteractionLog, ScriptedProvider
from app.workflow import (
    QUICK_DEBATE_STAGES,
    WorkflowError,
    check_stages,
    run_adversarial_trial,
)
from app.agents.advocate import AdvocateAgentError

from .conftest import defense_turn, prosecution_turn


def judge_step(decision_with, considered):
    return decision_with(lambda d: d.__setitem__("arguments_considered", list(considered)))


def full_trial_providers(decision_with):
    """Separate scripted providers for each role, for the default stage plan"""
    prosecution = ScriptedProvider(
        [
            prosecution_turn(),                     # PR-OPEN
            prosecution_turn(["DF-OPEN-1"]),        # PR-ARG
            prosecution_turn(["DF-ARG-1"]),         # PR-REB
            prosecution_turn(),                     # PR-CLOSE
        ]
    )
    defense = ScriptedProvider(
        [
            defense_turn(["PR-OPEN-1"]),            # DF-OPEN
            defense_turn(["PR-ARG-2"]),             # DF-ARG
            defense_turn(["PR-REB-1", "PR-REB-2"]), # DF-REB
            defense_turn(),                         # DF-CLOSE
        ]
    )
    judge = ScriptedProvider([judge_step(decision_with, ["PR-ARG-1", "DF-REB-2"])])
    return prosecution, defense, judge


@pytest.fixture
def trial(decision_with):
    prosecution, defense, judge = full_trial_providers(decision_with)
    log = InteractionLog()
    run = run_adversarial_trial(
        "CASE_001",
        prosecution_provider=prosecution,
        defense_provider=defense,
        judge_provider=judge,
        log=log,
        evidence=False,
        jury=False,
    )
    return run, prosecution, defense, judge, log


class TestFullTrial:
    def test_turns_follow_the_court_procedure(self, trial):
        run = trial[0]
        assert [(t.stage, t.role.value) for t in run.turns] == [
            (CourtStage.PROSECUTION_OPENING, "prosecution"),
            (CourtStage.DEFENSE_OPENING, "defense"),
            (CourtStage.PROSECUTION_ARGUMENT, "prosecution"),
            (CourtStage.DEFENSE_ARGUMENT, "defense"),
            (CourtStage.PROSECUTION_REBUTTAL, "prosecution"),
            (CourtStage.DEFENSE_REBUTTAL, "defense"),
            (CourtStage.CLOSING_ARGUMENTS, "prosecution"),
            (CourtStage.CLOSING_ARGUMENTS, "defense"),
        ]

    def test_argument_ids_are_unique_and_attributed(self, trial):
        run = trial[0]
        ids = [a.argument_id for a in run.arguments]
        assert len(ids) == len(set(ids)) == 16
        assert all(a.argument_id.startswith("PR-") for a in run.prosecution_arguments)
        assert all(a.argument_id.startswith("DF-") for a in run.defense_arguments)

    def test_rebuttals_reference_the_other_side(self, trial):
        run = trial[0]
        rebuttal = next(t for t in run.turns if t.stage == CourtStage.DEFENSE_REBUTTAL)
        assert rebuttal.arguments[0].counter_argument_ids == ["PR-REB-1", "PR-REB-2"]

    def test_each_advocate_sees_the_debate_so_far(self, trial):
        _, prosecution, defense, _, _ = trial
        opening_prompt = defense.requests[0].messages[0].content
        assert '"argument_id": "PR-OPEN-1"' in opening_prompt
        assert "DF-" not in opening_prompt.split("<case_record>")[1].split("</case_record>")[0]
        closing_prompt = prosecution.requests[3].messages[0].content
        assert '"argument_id": "DF-REB-2"' in closing_prompt

    def test_every_turn_is_a_structured_message(self, trial):
        run = trial[0]
        assert len(run.messages) == 9
        assert [m.message_type for m in run.messages[:2]] == [MessageType.OPENING_STATEMENT] * 2
        assert run.messages[4].message_type == MessageType.REBUTTAL
        decision = run.messages[-1]
        assert decision.message_type == MessageType.DECISION
        assert decision.sender == "judge_agent"
        assert decision.argument_ids == ["PR-ARG-1", "DF-REB-2"]

    def test_judge_receives_every_argument(self, trial):
        judge = trial[3]
        prompt = judge.requests[0].messages[0].content
        record = json.loads(prompt.split("<case_record>\n")[1].split("\n</case_record>")[0])
        assert len(record["party_arguments"]) == 16
        assert {a["party"] for a in record["party_arguments"]} == {
            "prosecution_agent",
            "defense_agent",
        }
        assert "at least one from each party" in prompt

    def test_event_history(self, trial):
        run = trial[0]
        kinds = [e["event_type"] for e in run.event_history]
        assert kinds[:2] == ["CASE_LOADED", "RULES_EVALUATED"]
        assert kinds.count("AGENT_ARGUMENT") == 8
        assert kinds[-2:] == ["JUDGE_DECISION", "CASE_COMPLETE"]
        argument_event = run.event_history[3]
        assert argument_event["argument_ids"] == ["PR-OPEN-1", "PR-OPEN-2"]
        assert argument_event["stage"] == "PROSECUTION_OPENING"

    def test_every_call_is_logged(self, trial):
        log = trial[4]
        agents = [r.agent_id for r in log.records]
        assert agents.count("prosecution_agent") == 4
        assert agents.count("defense_agent") == 4
        assert agents.count("judge_agent") == 1
        assert all(r.validation_passed for r in log.records)

    def test_verdict_and_usage(self, trial):
        run = trial[0]
        assert run.judgment.verdict.decision == "burglary: not_guilty; assault: not_guilty"
        assert run.usage.output_tokens > 0

    def test_run_serialises(self, trial):
        data = json.loads(trial[0].model_dump_json())
        assert len(data["turns"]) == 8
        assert data["judgment"]["verdict"]["case_id"] == "CASE_001"


class TestTrialVariants:
    def test_single_shared_provider(self, decision_with):
        steps = [
            prosecution_turn(),
            defense_turn(["PR-OPEN-1"]),
            prosecution_turn(),
            defense_turn(),
            judge_step(decision_with, ["PR-OPEN-1", "DF-OPEN-1"]),
        ]
        run = run_adversarial_trial(
            "CASE_001",
            ScriptedProvider(steps),
            stages=QUICK_DEBATE_STAGES,
            evidence=False,
            jury=False,
        )
        assert len(run.turns) == 4
        assert [a.argument_id for a in run.arguments][-2:] == ["DF-CLOSE-1", "DF-CLOSE-2"]

    def test_repeated_stage_gets_a_round_number(self, decision_with):
        stages = [
            CourtStage.PROSECUTION_OPENING,
            CourtStage.DEFENSE_OPENING,
            CourtStage.PROSECUTION_REBUTTAL,
            CourtStage.DEFENSE_REBUTTAL,
            CourtStage.PROSECUTION_REBUTTAL,
        ]
        steps = [
            prosecution_turn(),
            defense_turn(),
            prosecution_turn(["DF-OPEN-1"]),
            defense_turn(["PR-REB-1"]),
            prosecution_turn(["DF-REB-1"]),
            judge_step(decision_with, ["PR-REB2-1", "DF-REB-1"]),
        ]
        run = run_adversarial_trial(
            "CASE_001", ScriptedProvider(steps), stages=stages, evidence=False, jury=False
        )
        assert run.turns[-1].arguments[0].argument_id == "PR-REB2-1"

    def test_judge_ignoring_one_side_is_rejected(self, decision_with):
        steps = [
            prosecution_turn(),
            defense_turn(),
            prosecution_turn(),
            defense_turn(),
            judge_step(decision_with, ["PR-OPEN-1"]),               # ignores the defense
            judge_step(decision_with, ["PR-OPEN-1", "DF-OPEN-2"]),
        ]
        run = run_adversarial_trial(
            "CASE_001",
            ScriptedProvider(steps),
            stages=QUICK_DEBATE_STAGES,
            evidence=False,
            jury=False,
        )
        attempts = run.judgment.attempts
        assert [a.accepted for a in attempts] == [False, True]
        assert "No argument from defense_agent" in attempts[0].errors[0]

    def test_advocate_failure_stops_the_trial(self):
        with pytest.raises(AdvocateAgentError):
            run_adversarial_trial(
                "CASE_001",
                ScriptedProvider(["bad"] * 3),
                stages=QUICK_DEBATE_STAGES,
                evidence=False, jury=False,
            )

    def test_missing_provider(self):
        with pytest.raises(WorkflowError, match="provider"):
            run_adversarial_trial("CASE_001", prosecution_provider=ScriptedProvider([]))

    def test_unknown_case(self):
        with pytest.raises(WorkflowError, match="Unknown case"):
            run_adversarial_trial("CASE_404", ScriptedProvider([]))


class TestStagePlan:
    def test_default_and_quick_plans_are_valid(self):
        check_stages(QUICK_DEBATE_STAGES)

    def test_empty_plan(self):
        with pytest.raises(WorkflowError, match="at least one"):
            check_stages([])

    def test_non_debate_stage(self):
        with pytest.raises(WorkflowError, match="not an adversarial debate stage"):
            check_stages([CourtStage.PROSECUTION_OPENING, CourtStage.JURY_DELIBERATION])

    def test_rebuttal_before_the_other_side_spoke(self):
        with pytest.raises(WorkflowError, match="cannot come before"):
            check_stages([CourtStage.PROSECUTION_OPENING, CourtStage.PROSECUTION_REBUTTAL])


class TestTrialCli:
    def test_show_prompt(self, capsys):
        assert main(["trial", "CASE_001", "--show-prompt"]) == 0
        out = capsys.readouterr().out
        assert "You are the prosecutor" in out
        assert "Stage: PROSECUTION_OPENING" in out

    def test_quick_trial(self, monkeypatch, capsys, tmp_path, decision_with):
        steps = [
            prosecution_turn(),
            defense_turn(["PR-OPEN-1"]),
            prosecution_turn(),
            defense_turn(),
            judge_step(decision_with, ["PR-OPEN-1", "DF-OPEN-1"]),
        ]
        monkeypatch.setattr(
            "app.cli._build_provider", lambda args, settings: ScriptedProvider(steps)
        )
        log_file = tmp_path / "trial.jsonl"
        args = ["trial", "CASE_001", "--quick", "--no-evidence", "--no-jury"]
        args += ["--log-file", str(log_file)]
        assert main(args) == 0

        out = capsys.readouterr().out
        assert "[PROSECUTION_OPENING] prosecution_agent" in out
        assert "DF-OPEN-1:" in out
        assert "(answers PR-OPEN-1)" in out
        assert "assumes: David's account" in out
        assert "ARGUMENTS WEIGHED: PR-OPEN-1, DF-OPEN-1" in out
        assert "does not provide legal advice" in out
        assert len(log_file.read_text(encoding="utf-8").splitlines()) == 5

    def test_failed_trial_exits_non_zero(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(
            "app.cli._build_provider", lambda args, settings: ScriptedProvider(["bad"] * 3)
        )
        log_file = str(tmp_path / "l.jsonl")
        args = ["trial", "CASE_001", "--quick", "--no-evidence", "--no-jury"]
        code = main(args + ["--log-file", log_file])
        assert code == 1
        assert "Simulation failed" in capsys.readouterr().err
