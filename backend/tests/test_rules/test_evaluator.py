"""Tests for condition evaluation and witness reliability scoring"""

import pytest

from app.domain import BindingStance, Case, Witness
from app.rules import ConditionEvaluator, ConditionStatus, EvaluationPolicy
from app.rules.evaluator import assess_witness_reliability

from .conftest import binding


class TestReferenceWeights:
    """Weights derived from fact status and evidence reliability"""

    def test_fact_weight_by_status(self, case: Case):
        evaluator = ConditionEvaluator(case)
        weights = {f.fact_id: evaluator.fact_weight(f).weight for f in case.facts}
        assert weights == {"F1": 1.0, "F2": 0.5, "F3": 0.25}

    def test_evidence_weight_scales_with_type(self, case: Case):
        evaluator = ConditionEvaluator(case)
        weights = {e.evidence_id: evaluator.evidence_weight(e).weight for e in case.evidence}
        assert weights["EV1"] == pytest.approx(0.9)  # physical, factor 1.0
        assert weights["EV2"] == pytest.approx(0.51)  # testimonial, factor 0.85
        assert weights["EV3"] == pytest.approx(0.35)  # circumstantial, factor 0.7

    def test_weight_explanation_is_recorded(self, case: Case):
        evaluator = ConditionEvaluator(case)
        explanation = evaluator.evidence_weight(case.evidence[0]).explanation
        assert "reliability" in explanation
        assert "physical" in explanation


class TestConditionStatus:
    """The four condition outcomes"""

    def _evaluate(self, case: Case, bindings, policy=None):
        evaluator = ConditionEvaluator(case, policy)
        return evaluator.evaluate("RULE_A", "C1", "First element", bindings)

    def test_satisfied_by_established_fact(self, case: Case):
        result = self._evaluate(case, [binding("RULE_A", "C1", fact_ids=["F1"])])
        assert result.status == ConditionStatus.SATISFIED
        assert result.is_satisfied
        assert result.support_strength == 1.0
        assert result.supporting_fact_ids == ["F1"]

    def test_unsupported_when_no_bindings(self, case: Case):
        result = self._evaluate(case, [])
        assert result.status == ConditionStatus.UNSUPPORTED
        assert result.support_strength == 0.0
        assert result.contradiction_strength == 0.0

    def test_unsupported_when_support_is_too_weak(self, case: Case):
        result = self._evaluate(case, [binding("RULE_A", "C1", fact_ids=["F2"])])
        assert result.support_strength == 0.5  # below the 0.6 threshold
        assert result.status == ConditionStatus.UNSUPPORTED

    def test_disputed_when_supported_and_contradicted(self, case: Case):
        result = self._evaluate(
            case,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C1", BindingStance.CONTRADICTS, fact_ids=["F2"]),
            ],
        )
        assert result.status == ConditionStatus.DISPUTED
        assert result.supporting_fact_ids == ["F1"]
        assert result.contradicting_fact_ids == ["F2"]

    def test_unsatisfied_when_only_contradicted(self, case: Case):
        result = self._evaluate(
            case, [binding("RULE_A", "C1", BindingStance.CONTRADICTS, fact_ids=["F1"])]
        )
        assert result.status == ConditionStatus.UNSATISFIED
        assert result.contradiction_strength == 1.0

    def test_weak_contradiction_does_not_dispute(self, case: Case):
        result = self._evaluate(
            case,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C1", BindingStance.CONTRADICTS, evidence_ids=["EV3"]),
            ],
        )
        assert result.contradiction_strength == pytest.approx(0.35)  # below 0.4
        assert result.status == ConditionStatus.SATISFIED


class TestStrengthAggregation:
    """How multiple references combine"""

    def test_strength_is_the_strongest_reference(self, case: Case):
        evaluator = ConditionEvaluator(case)
        result = evaluator.evaluate(
            "RULE_A",
            "C1",
            "First element",
            [binding("RULE_A", "C1", fact_ids=["F2", "F3"], evidence_ids=["EV1"])],
        )
        assert result.support_strength == pytest.approx(0.9)
        assert len(result.weights) == 3

    def test_references_are_deduplicated(self, case: Case):
        evaluator = ConditionEvaluator(case)
        result = evaluator.evaluate(
            "RULE_A",
            "C1",
            "First element",
            [
                binding("RULE_A", "C1", fact_ids=["F1"], evidence_ids=["EV1"]),
                binding("RULE_A", "C1", fact_ids=["F1"], evidence_ids=["EV1"]),
            ],
        )
        assert result.supporting_fact_ids == ["F1"]
        assert result.supporting_evidence_ids == ["EV1"]

    def test_unknown_references_are_ignored(self, case: Case):
        evaluator = ConditionEvaluator(case)
        result = evaluator.evaluate(
            "RULE_A",
            "C1",
            "First element",
            [binding("RULE_A", "C1", fact_ids=["F_NOPE"], evidence_ids=["E_NOPE"])],
        )
        assert result.supporting_fact_ids == []
        assert result.status == ConditionStatus.UNSUPPORTED


class TestPolicyIsConfigurable:
    """Thresholds and weights live in the policy, not in the logic"""

    def test_lower_threshold_satisfies_disputed_fact(self, case: Case):
        lenient = EvaluationPolicy(satisfaction_threshold=0.4)
        evaluator = ConditionEvaluator(case, lenient)
        result = evaluator.evaluate(
            "RULE_A", "C1", "First element", [binding("RULE_A", "C1", fact_ids=["F2"])]
        )
        assert result.status == ConditionStatus.SATISFIED

    def test_strict_dispute_threshold_ignores_weak_contradiction(self, case: Case):
        strict = EvaluationPolicy(dispute_threshold=0.9)
        evaluator = ConditionEvaluator(case, strict)
        result = evaluator.evaluate(
            "RULE_A",
            "C1",
            "First element",
            [binding("RULE_A", "C1", BindingStance.CONTRADICTS, fact_ids=["F2"])],
        )
        assert result.status == ConditionStatus.UNSUPPORTED

    def test_evaluation_is_deterministic(self, case: Case):
        evaluator = ConditionEvaluator(case)
        bindings = [
            binding("RULE_A", "C1", fact_ids=["F1"]),
            binding("RULE_A", "C1", BindingStance.CONTRADICTS, evidence_ids=["EV2"]),
        ]
        first = evaluator.evaluate("RULE_A", "C1", "First element", bindings)
        second = evaluator.evaluate("RULE_A", "C1", "First element", bindings)
        assert first.model_dump() == second.model_dump()


class TestWitnessReliability:
    """Deterministic scoring under evidence rule E003"""

    def test_clean_witness_scores_high(self, case: Case):
        assessment = assess_witness_reliability(case.witnesses[0])
        assert assessment.reliability_score == 1.0
        assert assessment.challenge_grounds == []
        assert "no apparent bias" in assessment.positive_factors

    def test_bias_and_interest_reduce_score(self):
        witness = Witness(
            witness_id="WT2",
            name="Interested Witness",
            statement="He attacked me.",
            reliability_factors={
                "bias": "victim_in_case",
                "opportunity_to_observe": "high",
                "memory_quality": "good",
                "consistency": "statement_consistent",
                "personal_interest": "high",
            },
        )
        assessment = assess_witness_reliability(witness)
        assert assessment.reliability_score == pytest.approx(0.65)
        assert len(assessment.challenge_grounds) == 2

    def test_conflicting_impaired_witness_scores_low(self):
        witness = Witness(
            witness_id="WT3",
            name="Challenged Witness",
            statement="I do not remember clearly.",
            reliability_factors={
                "bias": "defendant_in_case",
                "opportunity_to_observe": "high",
                "memory_quality": "potentially_impaired_by_trauma",
                "consistency": "conflicts_with_other_evidence",
                "personal_interest": "very_high",
            },
        )
        assessment = assess_witness_reliability(witness)
        assert assessment.reliability_score == pytest.approx(0.15)
        assert "testimony conflicts with other evidence" in assessment.challenge_grounds
        assert "very high personal interest in the outcome" in assessment.challenge_grounds

    def test_unknown_factors_are_reported_not_scored(self):
        witness = Witness(
            witness_id="WT4",
            name="Odd Factors",
            statement="Statement",
            reliability_factors={"eyesight": "poor", "memory_quality": "unrecorded"},
        )
        assessment = assess_witness_reliability(witness)
        assert assessment.reliability_score == 1.0
        assert assessment.unscored_factors == ["eyesight: poor", "memory_quality: unrecorded"]

    def test_score_is_clamped_to_zero(self):
        witness = Witness(
            witness_id="WT5",
            name="Wholly Unreliable",
            statement="Statement",
            reliability_factors={
                "bias": "paid_by_a_party",
                "opportunity_to_observe": "none",
                "memory_quality": "poor",
                "consistency": "inconsistent",
                "personal_interest": "very_high",
            },
        )
        assessment = assess_witness_reliability(witness)
        assert assessment.reliability_score == 0.0
