"""Tests for Judge Agent output validation"""

from app.agents.judge import JudgeDecisionOutput, JudgeOutputValidator
from app.domain import Argument
from app.rules import ReferenceType


def validate(case, evaluation, decision, **kwargs):
    output = JudgeDecisionOutput.model_validate(decision)
    return JudgeOutputValidator(case, evaluation, **kwargs).validate(output)


class TestValidDecision:
    def test_valid_decision_passes(self, case, evaluation, valid_decision):
        report = validate(case, evaluation, valid_decision)
        assert report.valid, report.messages
        assert report.divergences == []

    def test_referenced_ids_are_collected(self, valid_decision):
        output = JudgeDecisionOutput.model_validate(valid_decision)
        assert "F004" in output.referenced_fact_ids()
        assert "E007" in output.referenced_evidence_ids()
        assert output.referenced_rule_ids()[:2] == ["LAW_104", "LAW_101"]


class TestReferenceErrors:
    def test_fabricated_evidence(self, case, evaluation, decision_with):
        decision = decision_with(lambda d: d["established_facts"][0]["evidence_ids"].append("E999"))
        report = validate(case, evaluation, decision)
        assert not report.valid
        assert report.reference_errors[0].reference_type == ReferenceType.EVIDENCE
        assert report.reference_errors[0].reference_id == "E999"

    def test_fabricated_fact(self, case, evaluation, decision_with):
        decision = decision_with(
            lambda d: d["charge_decisions"][0]["elements"][0]["fact_ids"].append("F099")
        )
        report = validate(case, evaluation, decision)
        assert [e.reference_id for e in report.reference_errors] == ["F099"]

    def test_fabricated_law(self, case, evaluation, decision_with):
        decision = decision_with(
            lambda d: d["applicable_rules"].append({"rule_id": "LAW_999", "relevance": "x"})
        )
        report = validate(case, evaluation, decision)
        assert report.reference_errors[0].reference_type == ReferenceType.LAW

    def test_unknown_argument(self, case, evaluation, decision_with):
        decision = decision_with(lambda d: d["arguments_considered"].append("ARG_1"))
        report = validate(case, evaluation, decision)
        assert report.reference_errors[0].reference_type == ReferenceType.ARGUMENT

    def test_presented_argument_is_accepted(self, case, evaluation, decision_with):
        argument = Argument(
            argument_id="ARG_1",
            agent_id="prosecution_agent",
            claim="Alex entered unlawfully",
            evidence_ids=["E001"],
            law_ids=["LAW_104"],
            reasoning="Broken window",
        )
        decision = decision_with(lambda d: d["arguments_considered"].append("ARG_1"))
        assert validate(case, evaluation, decision, arguments=[argument]).valid


class TestStructuralErrors:
    def test_missing_charge(self, case, evaluation, decision_with):
        decision = decision_with(lambda d: d["charge_decisions"].pop())
        report = validate(case, evaluation, decision)
        assert any("'assault' was not decided" in e for e in report.structural_errors)

    def test_duplicate_charge(self, case, evaluation, decision_with):
        decision = decision_with(
            lambda d: d["charge_decisions"].append(dict(d["charge_decisions"][0]))
        )
        report = validate(case, evaluation, decision)
        assert any("decided 2 times" in e for e in report.structural_errors)

    def test_invented_charge(self, case, evaluation, decision_with):
        def mutate(d):
            d["charge_decisions"][0]["charge"] = "trespass"

        report = validate(case, evaluation, decision_with(mutate))
        assert any("'trespass' is not one of the charges" in e for e in report.structural_errors)

    def test_charge_under_non_offense_rule(self, case, evaluation, decision_with):
        def mutate(d):
            d["charge_decisions"][0]["rule_id"] = "LAW_201"

        report = validate(case, evaluation, decision_with(mutate))
        assert any("not an offense" in e for e in report.structural_errors)

    def test_non_defense_listed_as_defense(self, case, evaluation, decision_with):
        decision = decision_with(
            lambda d: d["charge_decisions"][0]["defenses_considered"].append("LAW_101")
        )
        report = validate(case, evaluation, decision)
        assert any("not a defense rule" in e for e in report.structural_errors)

    def test_unknown_condition(self, case, evaluation, decision_with):
        def mutate(d):
            d["charge_decisions"][0]["elements"][1]["condition_id"] = "C7"

        report = validate(case, evaluation, decision_with(mutate))
        assert any("no condition 'C7'" in e for e in report.structural_errors)

    def test_missing_element(self, case, evaluation, decision_with):
        decision = decision_with(lambda d: d["charge_decisions"][1]["elements"].pop())
        report = validate(case, evaluation, decision)
        assert any("does not assess required element(s) C3" in e for e in report.structural_errors)

    def test_conviction_on_unproven_element(self, case, evaluation, decision_with):
        def mutate(d):
            d["charge_decisions"][0]["decision"] = "guilty"

        report = validate(case, evaluation, decision_with(mutate))
        errors = report.structural_errors
        assert any("element(s) C2 were not found established" in e for e in errors)


class TestEngineDivergence:
    def _convict_burglary(self, d):
        burglary = d["charge_decisions"][0]
        burglary["decision"] = "guilty"
        burglary["elements"][1]["assessment"] = "established"

    def test_conviction_without_engine_support_is_recorded(
        self, case, evaluation, decision_with
    ):
        report = validate(case, evaluation, decision_with(self._convict_burglary))
        assert report.valid  # internally coherent, so not rejected by default
        kinds = {d.kind for d in report.divergences}
        assert "conviction_without_engine_support" in kinds
        assert "element_assessment" in kinds  # C2 established vs engine 'unsupported'
        assert all(d.against_defendant for d in report.divergences)

    def test_strict_alignment_rejects_it(self, case, evaluation, decision_with):
        report = validate(
            case, evaluation, decision_with(self._convict_burglary), strict_engine_alignment=True
        )
        assert not report.valid
        assert any("Strict alignment" in e for e in report.structural_errors)

    def test_element_rejected_despite_engine_support(self, case, evaluation, decision_with):
        def mutate(d):
            d["charge_decisions"][0]["elements"][0]["assessment"] = "not_established"

        report = validate(case, evaluation, decision_with(mutate))
        assert report.valid
        divergence = report.divergences[0]
        assert divergence.condition_id == "C1"
        assert divergence.engine_view == "satisfied"
        assert divergence.against_defendant is False

    def test_disputed_fact_treated_as_established(self, case, evaluation, decision_with):
        decision = decision_with(
            lambda d: d["established_facts"].append(
                {"fact_id": "F004", "finding": "Alex attacked David", "evidence_ids": []}
            )
        )
        report = validate(case, evaluation, decision)
        assert report.divergences[0].kind == "disputed_fact_treated_as_established"
