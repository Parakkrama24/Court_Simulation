"""Integration tests: the jury inside the trial, and its CLI

The debate runs openings and closings only with the Evidence Agent off, so
these tests isolate what the jury adds.
"""

import json

import pytest

from app.agents.jury import JurorAgentError, JuryOutcome, JuryRule
from app.cli import main
from app.domain import CourtStage, MessageType
from app.llm import InteractionLog, ScriptedProvider
from app.workflow import QUICK_DEBATE_STAGES, WorkflowError, run_adversarial_trial

from .conftest import defense_turn, juror_verdict, prosecution_turn

CONSIDERED = ["PR-OPEN-1", "DF-OPEN-1"]


def judge_step(decision_with):
    return decision_with(lambda d: d.__setitem__("arguments_considered", list(CONSIDERED)))


def debate_providers(decision_with):
    return {
        "prosecution_provider": ScriptedProvider([prosecution_turn(), prosecution_turn()]),
        "defense_provider": ScriptedProvider([defense_turn(), defense_turn()]),
        "judge_provider": ScriptedProvider([judge_step(decision_with)]),
    }


@pytest.fixture
def trial(decision_with):
    """jury_3 votes guilty on assault alone, then is persuaded in deliberation"""
    jurors = [
        ScriptedProvider(
            [
                juror_verdict(considered=CONSIDERED),
                juror_verdict(considered=CONSIDERED, deliberation=True),
            ]
        ),
        ScriptedProvider(
            [
                juror_verdict(considered=CONSIDERED),
                juror_verdict(considered=CONSIDERED, deliberation=True),
            ]
        ),
        ScriptedProvider(
            [
                juror_verdict(assault="guilty", considered=CONSIDERED),
                juror_verdict(considered=CONSIDERED, deliberation=True),
            ]
        ),
    ]
    providers = debate_providers(decision_with)
    log = InteractionLog()
    run = run_adversarial_trial(
        "CASE_001",
        **providers,
        juror_providers=jurors,
        evidence=False,
        stages=QUICK_DEBATE_STAGES,
        log=log,
    )
    return run, jurors, providers, log


class TestJuryInTheTrial:
    def test_independent_prompts_contain_nothing_from_other_jurors(self, trial):
        _, jurors, _, _ = trial
        independent = [p.requests[0].messages[0].content for p in jurors]
        # Byte-identical: each juror's independent input is the trial record alone.
        assert independent[0] == independent[1] == independent[2]
        assert "<jury_room>" not in independent[0]
        assert "jury_" not in independent[0]

    def test_deliberation_prompts_show_the_whole_panel(self, trial):
        _, jurors, _, _ = trial
        room = jurors[0].requests[1].messages[0].content.split("<jury_room>\n")[1]
        room = json.loads(room.split("\n</jury_room>")[0])
        assert list(room) == ["jury_1", "jury_2", "jury_3"]
        assert room["jury_1"]["you"] is True
        assert room["jury_3"]["charge_verdicts"][1]["verdict"] == "guilty"

    def test_votes_before_and_after_deliberation(self, trial):
        result = trial[0].jury_result
        assert result.rule == JuryRule.UNANIMOUS
        assert result.independent[1].outcome == JuryOutcome.HUNG
        assert result.final[1].outcome == JuryOutcome.NOT_GUILTY
        assert [(c.juror_id, c.charge) for c in result.vote_changes] == [("jury_3", "assault")]
        assert result.independent_agreement < result.final_agreement == 1.0

    def test_changed_charges_on_the_deliberation_decision(self, trial):
        run = trial[0]
        assert [d.changed_charges for d in run.jury_deliberation] == [[], [], ["assault"]]

    def test_jury_verdicts_are_domain_verdicts(self, trial):
        verdicts = trial[0].jury_verdicts
        assert len(verdicts) == 6
        assert [v.agent_id for v in verdicts[:3]] == ["jury_1", "jury_2", "jury_3"]

    def test_the_judge_sees_the_jury_and_advocates_do_not(self, trial):
        _, _, providers, _ = trial
        judge_prompt = providers["judge_provider"].requests[0].messages[0].content
        record = json.loads(judge_prompt.split("<case_record>\n")[1].split("\n</case_record>")[0])
        assert record["jury"]["verdicts"][1] == {
            "charge": "assault",
            "outcome": "not_guilty",
            "guilty_votes": 0,
            "not_guilty_votes": 3,
            "unanimous": True,
        }
        assert record["jury"]["vote_changes_in_deliberation"] == 1
        closing = providers["prosecution_provider"].requests[1].messages[0].content
        assert '"jury"' not in closing

    def test_judge_jury_agreement(self, trial):
        run = trial[0]
        assert [row["agrees"] for row in run.judge_jury_agreement] == [True, True]
        decision_event = next(
            e for e in run.event_history if e["event_type"] == "JUDGE_DECISION"
        )
        assert decision_event["agrees_with_jury"] == {"burglary": True, "assault": True}

    def test_event_order(self, trial):
        run = trial[0]
        kinds = [
            (e["stage"], e["event_type"])
            for e in run.event_history
            if e["event_type"] != "AGENT_STARTED"
        ]
        closing = max(i for i, k in enumerate(kinds) if k[0] == "CLOSING_ARGUMENTS")
        assert kinds[closing + 1 : closing + 4] == [
            ("JURY_INDEPENDENT_DELIBERATION", "JURY_DECISION")
        ] * 3
        assert kinds[closing + 4 : closing + 7] == [("JURY_DELIBERATION", "JURY_DECISION")] * 3
        assert kinds[closing + 7] == ("JURY_DELIBERATION", "JURY_VERDICT")
        assert kinds[closing + 8][1] == "JUDGE_DECISION"
        verdict_event = run.event_history[
            [e["event_type"] for e in run.event_history].index("JURY_VERDICT")
        ]
        assert verdict_event["verdicts"] == {"burglary": "not_guilty", "assault": "not_guilty"}
        assert verdict_event["vote_changes"] == 1

    def test_messages_and_logging(self, trial):
        run, _, _, log = trial
        jury_messages = [m for m in run.messages if m.message_type == MessageType.JURY_VERDICT]
        assert len(jury_messages) == 6
        assert {m.stage for m in jury_messages} == {
            CourtStage.JURY_INDEPENDENT_DELIBERATION,
            CourtStage.JURY_DELIBERATION,
        }
        assert len(log.records) == 4 + 6 + 1
        assert run.usage.output_tokens > sum(t.usage.output_tokens for t in run.turns)

    def test_run_serialises(self, trial):
        data = json.loads(trial[0].model_dump_json())
        assert len(data["jury_independent"]) == 3
        assert data["jury_result"]["final"][1]["outcome"] == "not_guilty"


class TestJuryVariants:
    def test_no_deliberation(self, decision_with):
        jurors = [ScriptedProvider([juror_verdict(considered=CONSIDERED)]) for _ in range(3)]
        run = run_adversarial_trial(
            "CASE_001",
            **debate_providers(decision_with),
            juror_providers=jurors,
            evidence=False,
            stages=QUICK_DEBATE_STAGES,
            deliberation=False,
        )
        assert run.jury_deliberation == []
        assert not run.jury_result.deliberated
        assert all(p.remaining == 0 for p in jurors)

    def test_single_juror_does_not_deliberate(self, decision_with):
        run = run_adversarial_trial(
            "CASE_001",
            **debate_providers(decision_with),
            juror_providers=[ScriptedProvider([juror_verdict(considered=CONSIDERED)])],
            jurors=1,
            evidence=False,
            stages=QUICK_DEBATE_STAGES,
        )
        assert len(run.jury_independent) == 1
        assert run.jury_deliberation == []

    def test_majority_rule_and_perspectives(self, decision_with):
        jurors = [
            ScriptedProvider([juror_verdict(assault=vote, considered=CONSIDERED)])
            for vote in ("guilty", "guilty", "not_guilty")
        ]
        run = run_adversarial_trial(
            "CASE_001",
            **debate_providers(decision_with),
            juror_providers=jurors,
            juror_perspectives=["Background A.", None, "Background C."],
            jury_rule=JuryRule.MAJORITY,
            deliberation=False,
            evidence=False,
            stages=QUICK_DEBATE_STAGES,
        )
        assert run.jury_result.final[1].outcome == JuryOutcome.GUILTY
        assert jurors[0].requests[0].system.endswith("Background A.")
        assert "Your background" not in jurors[1].requests[0].system
        assert run.jury_independent[2].verdict.metadata["perspective"] == "Background C."
        # The judge acquits on assault; the disagreement is recorded, not hidden.
        assert run.judge_jury_agreement[1] == {
            "charge": "assault",
            "judge": "not_guilty",
            "jury": "guilty",
            "agrees": False,
        }

    def test_shared_provider(self, decision_with):
        steps = [
            prosecution_turn(),
            defense_turn(),
            prosecution_turn(),
            defense_turn(),
            *[juror_verdict(considered=CONSIDERED)] * 3,
            *[juror_verdict(considered=CONSIDERED, deliberation=True)] * 3,
            judge_step(decision_with),
        ]
        provider = ScriptedProvider(steps)
        run = run_adversarial_trial(
            "CASE_001", provider, evidence=False, stages=QUICK_DEBATE_STAGES
        )
        assert provider.remaining == 0
        assert run.jury_result.final_agreement == 1.0

    def test_juror_failure_stops_the_trial(self, decision_with):
        with pytest.raises(JurorAgentError, match="jury_1"):
            run_adversarial_trial(
                "CASE_001",
                **debate_providers(decision_with),
                juror_providers=[ScriptedProvider(["bad"] * 3) for _ in range(3)],
                evidence=False,
                stages=QUICK_DEBATE_STAGES,
            )

    @pytest.mark.parametrize("count", [0, 13])
    def test_juror_count_bounds(self, count):
        with pytest.raises(WorkflowError, match="between 1 and 12"):
            run_adversarial_trial("CASE_001", ScriptedProvider([]), jurors=count)

    def test_provider_count_must_match(self):
        with pytest.raises(WorkflowError, match="juror_providers has 2 entries for 3 jurors"):
            run_adversarial_trial(
                "CASE_001", ScriptedProvider([]), juror_providers=[ScriptedProvider([])] * 2
            )

    def test_perspective_count_must_match(self):
        with pytest.raises(WorkflowError, match="juror_perspectives has 1 entries"):
            run_adversarial_trial("CASE_001", ScriptedProvider([]), juror_perspectives=["x"])

    def test_missing_juror_provider(self):
        with pytest.raises(WorkflowError, match="missing: jury"):
            run_adversarial_trial(
                "CASE_001",
                prosecution_provider=ScriptedProvider([]),
                defense_provider=ScriptedProvider([]),
                judge_provider=ScriptedProvider([]),
                evidence=False,
            )


class TestJuryCli:
    def test_trial_prints_the_jury(self, monkeypatch, capsys, tmp_path, decision_with):
        steps = [
            prosecution_turn(),
            defense_turn(),
            prosecution_turn(),
            defense_turn(),
            juror_verdict(considered=CONSIDERED),
            juror_verdict(considered=CONSIDERED),
            juror_verdict(assault="guilty", considered=CONSIDERED),
            *[juror_verdict(considered=CONSIDERED, deliberation=True)] * 3,
            judge_step(decision_with),
        ]
        monkeypatch.setattr(
            "app.cli._build_provider", lambda args, settings: ScriptedProvider(steps)
        )
        log_file = str(tmp_path / "jury.jsonl")
        args = ["trial", "CASE_001", "--quick", "--no-evidence", "--log-file", log_file]
        assert main(args) == 0

        out = capsys.readouterr().out
        assert "[JURY_INDEPENDENT_DELIBERATION]" in out
        assert "jury_3" in out and "(changed: assault)" in out
        assert "[JURY VERDICT] rule: unanimous" in out
        assert "assault: NOT_GUILTY (0 guilty / 3 not guilty)" in out
        assert "agreement: 0.83 independent -> 1.00 after deliberation (1 vote change(s))" in out
        assert "burglary: judge agrees with jury" in out
        assert out.index("[JURY VERDICT]") < out.index("[JUDGE_DECISION]")

    def test_jury_options(self, monkeypatch, capsys, tmp_path, decision_with):
        steps = [
            prosecution_turn(),
            defense_turn(),
            prosecution_turn(),
            defense_turn(),
            *[juror_verdict(considered=CONSIDERED)] * 5,
            judge_step(decision_with),
        ]
        monkeypatch.setattr(
            "app.cli._build_provider", lambda args, settings: ScriptedProvider(steps)
        )
        args = [
            "trial", "CASE_001", "--quick", "--no-evidence", "--jurors", "5",
            "--jury-rule", "majority", "--no-deliberation",
            "--log-file", str(tmp_path / "j.jsonl"),
        ]
        assert main(args) == 0
        out = capsys.readouterr().out
        assert "[JURY VERDICT] rule: majority" in out
        assert "[JURY_DELIBERATION]" not in out
        assert "jury_5" in out
