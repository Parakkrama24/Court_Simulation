"""Integration tests: Case -> Judge Agent -> Decision, and the CLI"""

import json

import pytest

from app.cli import main
from app.llm import InteractionLog, ScriptedProvider
from app.workflow import WorkflowError, run_judge_only


class TestJudgeOnlyWorkflow:
    def test_runs_end_to_end(self, valid_decision):
        log = InteractionLog()
        run = run_judge_only("CASE_001", ScriptedProvider([valid_decision]), log=log)

        assert run.case.case_id == "CASE_001"
        assert run.evaluation.case_id == "CASE_001"
        assert run.result.verdict.decision == "burglary: not_guilty; assault: not_guilty"
        assert len(log.records) == 1

    def test_event_history_records_every_stage(self, valid_decision):
        run = run_judge_only("CASE_001", ScriptedProvider([valid_decision]))
        stages = [(e["stage"], e["event_type"]) for e in run.event_history]
        assert stages == [
            ("CASE_INITIALIZATION", "CASE_LOADED"),
            ("RULE_EVALUATION", "RULES_EVALUATED"),
            ("JUDGE_DECISION", "AGENT_STARTED"),
            ("JUDGE_DECISION", "JUDGE_DECISION"),
            ("CASE_COMPLETE", "CASE_COMPLETE"),
        ]
        assert all(e["timestamp"] for e in run.event_history)

    def test_rule_evaluation_event_summarises_the_engine(self, valid_decision):
        run = run_judge_only("CASE_001", ScriptedProvider([valid_decision]))
        rules = run.event_history[1]["rules"]
        assert rules["LAW_104/Alex Johnson"] == "indeterminate"
        assert rules["LAW_201/David Thompson"] == "not_satisfied"

    def test_decision_event_counts_rejections(self, valid_decision):
        run = run_judge_only("CASE_001", ScriptedProvider(["oops", valid_decision]))
        decision_event = run.event_history[3]
        assert decision_event["attempts"] == 2
        assert decision_event["rejected_attempts"] == 1

    def test_the_judge_receives_the_engine_evaluation(self, valid_decision):
        provider = ScriptedProvider([valid_decision])
        run_judge_only("CASE_001", provider)
        prompt = provider.requests[0].messages[0].content
        record = json.loads(prompt.split("<case_record>\n")[1].split("\n</case_record>")[0])
        statuses = {
            (r["rule_id"], r["subject"]): r["status"]
            for r in record["rule_engine_evaluation"]["rules"]
        }
        assert statuses[("LAW_101", "Alex Johnson")] == "not_satisfied"
        assert record["party_arguments"] == []

    def test_unknown_case(self):
        with pytest.raises(WorkflowError, match="Unknown case"):
            run_judge_only("CASE_404", ScriptedProvider([]))

    def test_run_serialises(self, valid_decision):
        run = run_judge_only("CASE_001", ScriptedProvider([valid_decision]))
        data = json.loads(run.model_dump_json())
        assert data["result"]["verdict"]["case_id"] == "CASE_001"


class TestCli:
    def test_show_prompt_calls_no_model(self, capsys):
        assert main(["judge", "CASE_001", "--show-prompt"]) == 0
        out = capsys.readouterr().out
        assert "=== SYSTEM ===" in out
        assert "=== USER ===" in out
        assert "<case_record>" in out

    def test_show_prompt_unknown_case(self, capsys):
        assert main(["judge", "CASE_404", "--show-prompt"]) == 2

    def test_run_with_a_provider(self, monkeypatch, capsys, tmp_path, valid_decision):
        monkeypatch.setattr(
            "app.cli._build_provider", lambda args, settings: ScriptedProvider([valid_decision])
        )
        log_file = tmp_path / "interactions.jsonl"
        assert main(["judge", "CASE_001", "--log-file", str(log_file)]) == 0

        out = capsys.readouterr().out
        assert "burglary [LAW_104]: NOT_GUILTY" in out
        assert "does not provide legal advice" in out
        assert len(log_file.read_text(encoding="utf-8").splitlines()) == 1

    def test_failed_run_exits_non_zero(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(
            "app.cli._build_provider", lambda args, settings: ScriptedProvider(["bad"] * 3)
        )
        code = main(["judge", "CASE_001", "--log-file", str(tmp_path / "log.jsonl")])
        assert code == 1
        assert "Simulation failed" in capsys.readouterr().err
