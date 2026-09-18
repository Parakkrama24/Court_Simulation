"""Tests for jury agents and the verdict engine"""

import pytest

from app.agents.judge.schema import ChargeOutcome
from app.agents.jury import (
    JurorAgent,
    JurorAgentError,
    JurorDeliberationOutput,
    JurorOutputValidator,
    JurorVerdictOutput,
    JuryOutcome,
    JuryRule,
    aggregate_jury,
    build_system_prompt,
    judge_jury_agreement,
    jury_context,
    tally_votes,
)
from app.domain import Argument, CourtStage, MessageType
from app.llm import InteractionLog, ScriptedProvider

from .conftest import juror_verdict

CHARGES = ["burglary", "assault"]
GUILTY = ChargeOutcome.GUILTY
NOT_GUILTY = ChargeOutcome.NOT_GUILTY


def output(**kwargs) -> JurorVerdictOutput:
    return JurorVerdictOutput.model_validate(juror_verdict(**kwargs))


def arguments():
    return [
        Argument(argument_id="PR-OPEN-1", agent_id="prosecution_agent", claim="c", reasoning="r"),
        Argument(argument_id="DF-OPEN-1", agent_id="defense_agent", claim="c", reasoning="r"),
    ]


# ============================================================================
# Verdict engine
# ============================================================================


class TestTally:
    def test_unanimous_acquittal(self):
        panel = {f"jury_{i}": output() for i in range(1, 4)}
        burglary, assault = tally_votes(panel, CHARGES)
        assert burglary.outcome == JuryOutcome.NOT_GUILTY
        assert burglary.unanimous
        assert burglary.agreement == 1.0
        assert burglary.not_guilty == ["jury_1", "jury_2", "jury_3"]

    def test_unanimous_conviction(self):
        panel = {f"jury_{i}": output(burglary="guilty") for i in range(1, 4)}
        assert tally_votes(panel, CHARGES)[0].outcome == JuryOutcome.GUILTY

    def test_split_under_unanimity_is_hung(self):
        panel = {
            "jury_1": output(),
            "jury_2": output(),
            "jury_3": output(assault="guilty"),
        }
        assault = tally_votes(panel, CHARGES)[1]
        assert assault.outcome == JuryOutcome.HUNG
        assert not assault.unanimous
        assert assault.agreement == pytest.approx(0.6667)
        assert assault.guilty == ["jury_3"]

    def test_majority_rule(self):
        panel = {
            "jury_1": output(assault="guilty"),
            "jury_2": output(assault="guilty"),
            "jury_3": output(),
        }
        assault = tally_votes(panel, CHARGES, JuryRule.MAJORITY)[1]
        assert assault.outcome == JuryOutcome.GUILTY
        assert not assault.unanimous

    def test_majority_tie_is_hung(self):
        panel = {"jury_1": output(assault="guilty"), "jury_2": output()}
        assert tally_votes(panel, CHARGES, JuryRule.MAJORITY)[1].outcome == JuryOutcome.HUNG

    def test_empty_jury(self):
        with pytest.raises(ValueError):
            tally_votes({}, CHARGES)


class TestAggregate:
    def test_deliberation_changes_are_recorded(self):
        independent = {
            "jury_1": output(),
            "jury_2": output(),
            "jury_3": output(assault="guilty"),
        }
        final = {"jury_1": output(), "jury_2": output(), "jury_3": output()}
        result = aggregate_jury(independent, CHARGES, deliberation=final)

        assert result.deliberated
        assert result.independent[1].outcome == JuryOutcome.HUNG
        assert result.final[1].outcome == JuryOutcome.NOT_GUILTY
        assert len(result.vote_changes) == 1
        change = result.vote_changes[0]
        assert (change.juror_id, change.charge, change.before, change.after) == (
            "jury_3",
            "assault",
            GUILTY,
            NOT_GUILTY,
        )
        assert result.independent_agreement == pytest.approx(0.8333, abs=1e-4)
        assert result.final_agreement == 1.0

    def test_without_deliberation(self):
        independent = {"jury_1": output(), "jury_2": output()}
        result = aggregate_jury(independent, CHARGES)
        assert not result.deliberated
        assert result.final == result.independent
        assert result.vote_changes == []
        assert result.outcome("burglary") == JuryOutcome.NOT_GUILTY
        assert result.outcome("arson") is None

    def test_judge_jury_agreement(self):
        independent = {"jury_1": output(assault="guilty"), "jury_2": output()}
        result = aggregate_jury(independent, CHARGES)
        rows = judge_jury_agreement({"burglary": NOT_GUILTY, "assault": NOT_GUILTY}, result)
        assert rows == [
            {"charge": "burglary", "judge": "not_guilty", "jury": "not_guilty", "agrees": True},
            {"charge": "assault", "judge": "not_guilty", "jury": "hung", "agrees": False},
        ]

    def test_jury_context_is_plain_data(self):
        result = aggregate_jury({"jury_1": output(), "jury_2": output()}, CHARGES)
        context = jury_context(result)
        assert context["rule"] == "unanimous"
        assert context["verdicts"][0] == {
            "charge": "burglary",
            "outcome": "not_guilty",
            "guilty_votes": 0,
            "not_guilty_votes": 2,
            "unanimous": True,
        }


# ============================================================================
# Validation
# ============================================================================


def validate(case, data, args=(), previous=None, schema=JurorVerdictOutput):
    return JurorOutputValidator(case, args, previous=previous).validate(
        schema.model_validate(data)
    )


class TestJurorValidation:
    def test_valid_verdict(self, case):
        assert validate(case, juror_verdict()).valid

    @pytest.mark.parametrize(
        "field,value,fragment",
        [
            ("evidence_ids", ["E404"], "E404"),
            ("fact_ids", ["F404"], "F404"),
            ("witness_ids", ["W404"], "W404"),
            ("rule_ids", ["LAW_104", "LAW_404"], "LAW_404"),
        ],
    )
    def test_fabricated_references(self, case, field, value, fragment):
        data = juror_verdict()
        data["charge_verdicts"][0][field] = value
        assert any(fragment in e for e in validate(case, data).errors)

    def test_unknown_argument(self, case):
        report = validate(case, juror_verdict(considered=["PR-OPEN-9"]), arguments())
        assert any("'PR-OPEN-9'" in e for e in report.errors)

    def test_every_charge_decided_once(self, case):
        data = juror_verdict()
        data["charge_verdicts"].pop()
        assert any("'assault' has no verdict" in e for e in validate(case, data).errors)
        data = juror_verdict()
        data["charge_verdicts"].append(dict(data["charge_verdicts"][0]))
        assert any("'burglary' has 2 verdicts" in e for e in validate(case, data).errors)

    def test_invented_charge(self, case):
        data = juror_verdict()
        data["charge_verdicts"][0]["charge"] = "arson"
        assert any("'arson' is not a charge" in e for e in validate(case, data).errors)

    def test_verdict_needs_an_offense_rule(self, case):
        data = juror_verdict()
        data["charge_verdicts"][0]["rule_ids"] = ["P002", "LAW_201"]
        assert any("relies on no offense rule" in e for e in validate(case, data).errors)

    def test_guilty_verdict_needs_the_record(self, case):
        data = juror_verdict(burglary="guilty")
        for field in ("fact_ids", "evidence_ids", "witness_ids"):
            data["charge_verdicts"][0][field] = []
        assert any("P003" in e for e in validate(case, data).errors)

    def test_not_guilty_may_rest_on_absence_of_proof(self, case):
        data = juror_verdict()
        for field in ("fact_ids", "evidence_ids", "witness_ids"):
            data["charge_verdicts"][0][field] = []
        assert validate(case, data).valid

    def test_both_sides_must_be_weighed(self, case):
        report = validate(case, juror_verdict(considered=["PR-OPEN-1"]), arguments())
        assert any("No argument from defense_agent" in e for e in report.errors)
        both = juror_verdict(considered=["PR-OPEN-1", "DF-OPEN-1"])
        assert validate(case, both, arguments()).valid

    def test_changed_vote_must_cite_the_record(self, case):
        previous = output(assault="guilty")
        data = juror_verdict(deliberation=True)
        for field in ("fact_ids", "evidence_ids", "witness_ids"):
            data["charge_verdicts"][1][field] = []
        report = validate(case, data, previous=previous, schema=JurorDeliberationOutput)
        assert any("changed your verdict on 'assault'" in e for e in report.errors)

    def test_changed_vote_with_citations_passes(self, case):
        report = validate(
            case,
            juror_verdict(deliberation=True),
            previous=output(assault="guilty"),
            schema=JurorDeliberationOutput,
        )
        assert report.valid

    def test_unchanged_vote_needs_no_new_citations(self, case):
        data = juror_verdict(deliberation=True)
        for field in ("fact_ids", "evidence_ids", "witness_ids"):
            data["charge_verdicts"][0][field] = []
        report = validate(case, data, previous=output(), schema=JurorDeliberationOutput)
        assert report.valid


# ============================================================================
# Agent
# ============================================================================


class TestJurorAgent:
    def test_system_prompt(self):
        prompt = build_system_prompt("jury_2")
        assert prompt.startswith("You are jury_2")
        assert "does not provide legal advice" in prompt
        assert "P004" in prompt
        assert "Your background" not in prompt

    def test_perspective_is_appended(self):
        prompt = build_system_prompt("jury_1", "You are a retired engineer.")
        assert prompt.endswith("## Your background\n\nYou are a retired engineer.")

    def test_independent_request_has_no_jury_room(self, case, evaluation):
        request = JurorAgent("jury_1", ScriptedProvider([])).build_independent_request(
            case, evaluation
        )
        content = request.messages[0].content
        assert "<jury_room>" not in content
        assert "Stage: JURY_INDEPENDENT_DELIBERATION" in content
        assert request.schema_name == "juror_verdict"

    def test_deliberation_request_shows_the_panel(self, case, evaluation):
        panel = {"jury_1": output(), "jury_2": output(assault="guilty")}
        request = JurorAgent("jury_2", ScriptedProvider([])).build_deliberation_request(
            case, evaluation, [], None, panel
        )
        content = request.messages[0].content
        room = content.split("<jury_room>\n")[1].split("\n</jury_room>")[0]
        assert '"jury_1"' in room and '"jury_2"' in room
        assert request.schema_name == "juror_deliberation"
        assert "not because of how many jurors voted" in content

    def test_decide_independently(self, case, evaluation):
        log = InteractionLog()
        agent = JurorAgent("jury_1", ScriptedProvider([juror_verdict()]), log=log)
        decision = agent.decide_independently(case, evaluation)
        assert decision.stage == CourtStage.JURY_INDEPENDENT_DELIBERATION
        assert decision.changed_charges == []
        verdict = decision.verdict
        assert verdict.verdict_id == "V_CASE_001_JURY_1_IND"
        assert verdict.agent_id == "jury_1"
        assert verdict.decision == "burglary: not_guilty; assault: not_guilty"
        assert verdict.laws_used == ["LAW_104", "P002", "LAW_101", "P004"]
        assert verdict.evidence_used == ["E001", "E002", "E007"]
        assert verdict.unresolved_questions == ["What Alex intended when he entered."]
        assert decision.message.message_type == MessageType.JURY_VERDICT
        assert decision.message.message_id == "MSG-JURY_1-IND"
        assert log.records[0].agent_id == "jury_1"

    def test_deliberate_reports_changed_charges(self, case, evaluation):
        panel = {"jury_1": output(assault="guilty"), "jury_2": output()}
        agent = JurorAgent("jury_1", ScriptedProvider([juror_verdict(deliberation=True)]))
        decision = agent.deliberate(case, evaluation, [], None, panel)
        assert decision.stage == CourtStage.JURY_DELIBERATION
        assert decision.changed_charges == ["assault"]
        assert decision.message.metadata == {"changed_charges": ["assault"]}
        assert decision.verdict.verdict_id.endswith("_DELIB")

    def test_deliberate_needs_own_decision(self, case, evaluation):
        agent = JurorAgent("jury_9", ScriptedProvider([]))
        with pytest.raises(ValueError, match="no independent decision"):
            agent.deliberate(case, evaluation, [], None, {"jury_1": output()})

    def test_invalid_verdict_is_regenerated(self, case, evaluation):
        bad = juror_verdict()
        bad["charge_verdicts"].pop()
        provider = ScriptedProvider([bad, juror_verdict()])
        decision = JurorAgent("jury_1", provider).decide_independently(case, evaluation)
        assert [a.accepted for a in decision.attempts] == [False, True]
        assert "'assault' has no verdict" in provider.requests[1].messages[2].content

    def test_gives_up(self, case, evaluation):
        agent = JurorAgent("jury_1", ScriptedProvider(["x", "y"]), max_attempts=2)
        with pytest.raises(JurorAgentError, match="jury_1"):
            agent.decide_independently(case, evaluation)
