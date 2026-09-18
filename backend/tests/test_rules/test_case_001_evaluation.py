"""End-to-end evaluation of CASE_001 with the seeded legal rules

These tests pin the conclusions the engine draws from the real case record.
They are the regression net for the whole Phase 2 pipeline:

    seed case + seed bindings -> conditions -> rules -> effects
"""

import pytest

from app.rules import (
    CASE_WIDE_SUBJECT,
    ConditionStatus,
    ReferenceValidator,
    RuleEngine,
    RuleStatus,
    get_default_registry,
)
from app.seed import get_case_001_bindings, get_case_by_id

ALEX = "Alex Johnson"
DAVID = "David Thompson"


@pytest.fixture(scope="module")
def case():
    return get_case_by_id("CASE_001")


@pytest.fixture(scope="module")
def bindings():
    return get_case_001_bindings()


@pytest.fixture(scope="module")
def evaluation(case, bindings):
    return RuleEngine().evaluate_case(case, bindings)


def rule(evaluation, rule_id, subject):
    results = evaluation.for_rule(rule_id, subject)
    assert results, f"no evaluation for {rule_id} / {subject}"
    return results[0]


def condition(evaluation, rule_id, subject, condition_id):
    for item in rule(evaluation, rule_id, subject).conditions:
        if item.condition_id == condition_id:
            return item
    raise AssertionError(f"no condition {condition_id} in {rule_id}")


class TestSeededBindings:
    """The bindings themselves must be grounded in the case record"""

    def test_all_bindings_reference_real_material(self, case, bindings):
        result = ReferenceValidator(case, get_default_registry()).validate_bindings(bindings)
        assert result.valid, result.messages

    def test_binding_ids_are_unique(self, bindings):
        ids = [b.binding_id for b in bindings]
        assert len(ids) == len(set(ids))

    def test_bindings_only_target_applicable_laws(self, case, bindings):
        assert {b.rule_id for b in bindings} <= set(case.applicable_laws)

    def test_bindings_only_concern_the_two_parties(self, bindings):
        assert {b.subject for b in bindings} == {ALEX, DAVID}


class TestBurglaryCharge:
    """LAW_104 against Alex Johnson - entry proven, intent not"""

    def test_unauthorized_entry_is_established(self, evaluation):
        entry = condition(evaluation, "LAW_104", ALEX, "C1")
        assert entry.status == ConditionStatus.SATISFIED
        assert entry.supporting_fact_ids == ["F001", "F002"]
        assert entry.supporting_evidence_ids == ["E001", "E002"]

    def test_intent_element_is_unsupported(self, evaluation):
        intent = condition(evaluation, "LAW_104", ALEX, "C2")
        assert intent.status == ConditionStatus.UNSUPPORTED
        assert intent.supporting_evidence_ids == []

    def test_burglary_cannot_be_established_on_this_record(self, evaluation):
        burglary = rule(evaluation, "LAW_104", ALEX)
        assert burglary.status == RuleStatus.INDETERMINATE
        assert burglary.effect_applies is False
        assert burglary.unsupported_conditions == ["C2"]


class TestAssaultChargeAgainstAlex:
    """LAW_101 against Alex Johnson - the alleged attack is not made out"""

    def test_force_and_contact_are_contradicted(self, evaluation):
        assert condition(evaluation, "LAW_101", ALEX, "C1").status == ConditionStatus.UNSATISFIED
        assert condition(evaluation, "LAW_101", ALEX, "C2").status == ConditionStatus.UNSATISFIED

    def test_absence_of_defensive_wounds_is_the_contradicting_evidence(self, evaluation):
        force = condition(evaluation, "LAW_101", ALEX, "C1")
        assert force.contradicting_evidence_ids == ["E007"]
        assert force.contradiction_strength == pytest.approx(0.85)

    def test_testimonial_support_falls_short_of_the_threshold(self, evaluation):
        force = condition(evaluation, "LAW_101", ALEX, "C1")
        assert force.support_strength == pytest.approx(0.595)  # 0.70 testimonial x 0.85

    def test_assault_charge_is_not_established(self, evaluation):
        assault = rule(evaluation, "LAW_101", ALEX)
        assert assault.status == RuleStatus.NOT_SATISFIED
        assert assault.effect_applies is False


class TestDavidsUseOfForce:
    """LAW_101 / LAW_102 applied to David Thompson"""

    def test_force_and_contact_are_established(self, evaluation):
        assert condition(evaluation, "LAW_101", DAVID, "C1").status == ConditionStatus.SATISFIED
        assert condition(evaluation, "LAW_101", DAVID, "C2").status == ConditionStatus.SATISFIED

    def test_unlawfulness_is_disputed(self, evaluation):
        unlawful = condition(evaluation, "LAW_101", DAVID, "C3")
        assert unlawful.status == ConditionStatus.DISPUTED
        assert unlawful.contradicting_fact_ids == ["F004"]

    def test_assault_by_david_is_indeterminate(self, evaluation):
        assert rule(evaluation, "LAW_101", DAVID).status == RuleStatus.INDETERMINATE

    def test_serious_injury_is_established(self, evaluation):
        injury = condition(evaluation, "LAW_102", DAVID, "C2")
        assert injury.status == ConditionStatus.SATISFIED
        assert injury.supporting_evidence_ids == ["E004"]

    def test_aggravated_assault_inherits_the_assault_question(self, evaluation):
        derived = condition(evaluation, "LAW_102", DAVID, "C1")
        assert derived.depends_on_rule == "LAW_101"
        assert derived.status == ConditionStatus.DISPUTED
        assert rule(evaluation, "LAW_102", DAVID).status == RuleStatus.INDETERMINATE


class TestSelfDefense:
    """LAW_201 / LAW_202 - the defensive force question"""

    def test_reasonable_belief_is_established(self, evaluation):
        belief = condition(evaluation, "LAW_201", DAVID, "C1")
        assert belief.status == ConditionStatus.SATISFIED
        assert "E005" in belief.supporting_evidence_ids

    def test_necessity_is_contradicted_by_the_absence_of_a_weapon(self, evaluation):
        necessity = condition(evaluation, "LAW_201", DAVID, "C2")
        assert necessity.status == ConditionStatus.UNSATISFIED
        assert necessity.contradicting_evidence_ids == ["E008"]

    def test_proportionality_has_no_support_at_all(self, evaluation):
        proportionality = condition(evaluation, "LAW_201", DAVID, "C3")
        assert proportionality.status == ConditionStatus.UNSATISFIED
        assert proportionality.support_strength == 0.0

    def test_self_defense_is_not_made_out_on_this_record(self, evaluation):
        defense = rule(evaluation, "LAW_201", DAVID)
        assert defense.status == RuleStatus.NOT_SATISFIED
        assert defense.effect_applies is False
        assert defense.unsatisfied_conditions == ["C2", "C3"]

    def test_excessive_force_remains_contested(self, evaluation):
        excessive = rule(evaluation, "LAW_202", DAVID)
        assert excessive.status == RuleStatus.INDETERMINATE
        assert excessive.disputed_conditions == ["C2"]


class TestPrinciplesAndSummary:
    """Case-wide principles and the evaluation summary"""

    def test_principles_apply_unconditionally(self, evaluation):
        for rule_id in ["P001", "P002", "P003", "P004", "P005"]:
            principle = rule(evaluation, rule_id, CASE_WIDE_SUBJECT)
            assert principle.status == RuleStatus.UNCONDITIONAL
            assert principle.effect_applies

    def test_no_offense_or_defense_effect_is_triggered(self, evaluation):
        triggered = {
            e.rule_id for e in evaluation.rule_evaluations if e.effect_applies
        }
        assert triggered == {"P001", "P002", "P003", "P004", "P005"}

    def test_every_applicable_law_was_evaluated(self, evaluation, case):
        evaluated = {e.rule_id for e in evaluation.rule_evaluations}
        assert set(case.applicable_laws) <= evaluated
        assert evaluation.unevaluated_rules == []

    def test_contested_elements_are_reported_as_conflicts(self, evaluation):
        conflicts = [
            (c["rule_id"], c.get("condition_id"))
            for c in evaluation.conflicting_evidence
            if c["type"] == "condition_conflict"
        ]
        assert ("LAW_101", "C3") in conflicts
        assert ("LAW_202", "C2") in conflicts

    def test_witness_reliability_reflects_bias_and_interest(self, evaluation):
        scores = {w.witness_id: w.reliability_score for w in evaluation.witness_assessments}
        assert scores["W002"] > scores["W001"] > scores["W003"]
        assert scores["W002"] == pytest.approx(0.95)

    def test_defendants_own_account_is_the_least_reliable(self, evaluation):
        alex = next(w for w in evaluation.witness_assessments if w.witness_id == "W003")
        assert "testimony conflicts with other evidence" in alex.challenge_grounds

    def test_evaluation_is_reproducible(self, case, bindings, evaluation):
        assert RuleEngine().evaluate_case(case, bindings).model_dump() == evaluation.model_dump()
