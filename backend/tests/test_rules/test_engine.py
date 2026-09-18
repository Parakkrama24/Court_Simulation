"""Tests for rule-level and case-level evaluation"""

import pytest

from app.domain import BindingStance, Case, FactStatus
from app.rules import (
    CASE_WIDE_SUBJECT,
    ConditionStatus,
    EvaluationPolicy,
    LegalRuleRegistry,
    RuleEngine,
    RuleStatus,
)

from .conftest import SUBJECT, binding


@pytest.fixture
def engine(registry: LegalRuleRegistry) -> RuleEngine:
    return RuleEngine(registry)


class TestRuleStatus:
    """Aggregating condition results into a rule status"""

    def test_satisfied_when_all_required_conditions_hold(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(
            case,
            "RULE_A",
            SUBJECT,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C2", evidence_ids=["EV1"]),
            ],
        )
        assert result.status == RuleStatus.SATISFIED
        assert result.effect_applies
        assert result.effect == "rule_a_established"
        assert result.satisfied_conditions == ["C1", "C2"]

    def test_not_satisfied_when_a_condition_is_contradicted(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(
            case,
            "RULE_A",
            SUBJECT,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C2", BindingStance.CONTRADICTS, fact_ids=["F1"]),
            ],
        )
        assert result.status == RuleStatus.NOT_SATISFIED
        assert result.effect_applies is False
        assert result.unsatisfied_conditions == ["C2"]

    def test_indeterminate_when_a_condition_is_unsupported(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(
            case, "RULE_A", SUBJECT, [binding("RULE_A", "C1", fact_ids=["F1"])]
        )
        assert result.status == RuleStatus.INDETERMINATE
        assert result.unsupported_conditions == ["C2"]
        assert result.effect_applies is False

    def test_indeterminate_when_a_condition_is_disputed(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(
            case,
            "RULE_A",
            SUBJECT,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C2", fact_ids=["F1"]),
                binding("RULE_A", "C2", BindingStance.CONTRADICTS, fact_ids=["F2"]),
            ],
        )
        assert result.status == RuleStatus.INDETERMINATE
        assert result.disputed_conditions == ["C2"]

    def test_contradiction_outranks_open_questions(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(
            case,
            "RULE_A",
            SUBJECT,
            [binding("RULE_A", "C2", BindingStance.CONTRADICTS, fact_ids=["F1"])],
        )
        assert result.status == RuleStatus.NOT_SATISFIED

    def test_rule_without_conditions_is_unconditional(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(case, "RULE_C", CASE_WIDE_SUBJECT, [])
        assert result.status == RuleStatus.UNCONDITIONAL
        assert result.effect_applies
        assert result.conditions == []

    def test_optional_conditions_decide_when_none_are_required(
        self, engine: RuleEngine, case: Case
    ):
        result = engine.evaluate_rule(
            case,
            "RULE_OPT",
            SUBJECT,
            [
                binding("RULE_OPT", "C1", fact_ids=["F1"]),
                binding("RULE_OPT", "C2", evidence_ids=["EV1"]),
            ],
        )
        assert result.status == RuleStatus.SATISFIED

    def test_bindings_for_other_subjects_are_ignored(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(
            case,
            "RULE_A",
            SUBJECT,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C2", fact_ids=["F1"], subject="Someone Else"),
            ],
        )
        assert result.unsupported_conditions == ["C2"]

    def test_unknown_rule_raises(self, engine: RuleEngine, case: Case):
        with pytest.raises(KeyError):
            engine.evaluate_rule(case, "RULE_NOPE", SUBJECT, [])


class TestRuleDependencies:
    """Conditions resolved through another rule"""

    def test_satisfied_dependency_satisfies_condition(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(
            case,
            "RULE_B",
            SUBJECT,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C2", evidence_ids=["EV1"]),
                binding("RULE_B", "C2", fact_ids=["F1"]),
            ],
        )
        assert result.status == RuleStatus.SATISFIED
        derived = result.conditions[0]
        assert derived.depends_on_rule == "RULE_A"
        assert derived.status == ConditionStatus.SATISFIED
        assert "RULE_A" in derived.reasoning

    def test_failed_dependency_fails_condition(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(
            case,
            "RULE_B",
            SUBJECT,
            [
                binding("RULE_A", "C1", BindingStance.CONTRADICTS, fact_ids=["F1"]),
                binding("RULE_B", "C2", fact_ids=["F1"]),
            ],
        )
        assert result.status == RuleStatus.NOT_SATISFIED
        assert result.conditions[0].status == ConditionStatus.UNSATISFIED

    def test_indeterminate_dependency_disputes_condition(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(
            case,
            "RULE_B",
            SUBJECT,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_B", "C2", fact_ids=["F1"]),
            ],
        )
        assert result.status == RuleStatus.INDETERMINATE
        assert result.conditions[0].status == ConditionStatus.DISPUTED

    def test_derived_condition_carries_underlying_references(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(
            case,
            "RULE_B",
            SUBJECT,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C2", evidence_ids=["EV1"]),
                binding("RULE_B", "C2", fact_ids=["F1"]),
            ],
        )
        derived = result.conditions[0]
        assert derived.supporting_fact_ids == ["F1"]
        assert derived.supporting_evidence_ids == ["EV1"]

    def test_circular_dependency_terminates_and_is_reported(
        self, engine: RuleEngine, case: Case
    ):
        result = engine.evaluate_rule(case, "RULE_CYC1", SUBJECT, [])
        condition = result.conditions[0]
        assert result.status == RuleStatus.INDETERMINATE
        assert condition.metadata["circular_dependency"] is True
        assert "circular dependency" in condition.reasoning

    def test_missing_dependency_leaves_condition_unsupported(self, engine: RuleEngine, case: Case):
        result = engine.evaluate_rule(case, "RULE_MISSING_DEP", SUBJECT, [])
        condition = result.conditions[0]
        assert condition.status == ConditionStatus.UNSUPPORTED
        assert "unknown rule RULE_NOPE" in condition.reasoning


class TestCaseEvaluation:
    """Evaluating every applicable rule for a case"""

    def test_evaluates_applicable_laws_per_subject(self, engine: RuleEngine, case: Case):
        evaluation = engine.evaluate_case(
            case,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C2", evidence_ids=["EV1"]),
                binding("RULE_A", "C1", fact_ids=["F1"], subject="Second Party"),
            ],
        )
        subjects = {e.subject for e in evaluation.for_rule("RULE_A")}
        assert subjects == {SUBJECT, "Second Party"}

    def test_rules_without_bindings_are_reported(self, engine: RuleEngine, case: Case):
        evaluation = engine.evaluate_case(case, [binding("RULE_A", "C1", fact_ids=["F1"])])
        assert "RULE_B" in evaluation.unevaluated_rules

    def test_unknown_applicable_law_is_reported(self, engine: RuleEngine, case: Case):
        case.applicable_laws = ["RULE_A", "RULE_NOPE"]
        evaluation = engine.evaluate_case(case, [binding("RULE_A", "C1", fact_ids=["F1"])])
        assert "RULE_NOPE" in evaluation.unevaluated_rules

    def test_unconditional_rules_evaluate_case_wide(self, engine: RuleEngine, case: Case):
        evaluation = engine.evaluate_case(case, [])
        unconditional = evaluation.for_rule("RULE_C")
        assert len(unconditional) == 1
        assert unconditional[0].subject == CASE_WIDE_SUBJECT
        assert "rule_c_applies" in evaluation.applied_effects

    def test_bindings_from_other_cases_are_ignored(self, engine: RuleEngine, case: Case):
        evaluation = engine.evaluate_case(
            case, [binding("RULE_A", "C1", fact_ids=["F1"], case_id="OTHER_CASE")]
        )
        assert evaluation.for_rule("RULE_A") == []
        assert "RULE_A" in evaluation.unevaluated_rules

    def test_witness_assessments_are_included(self, engine: RuleEngine, case: Case):
        evaluation = engine.evaluate_case(case, [])
        assert [w.witness_id for w in evaluation.witness_assessments] == ["WT1"]

    def test_for_subject_filters_evaluations(self, engine: RuleEngine, case: Case):
        evaluation = engine.evaluate_case(
            case,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C1", fact_ids=["F1"], subject="Second Party"),
            ],
        )
        assert all(e.subject == SUBJECT for e in evaluation.for_subject(SUBJECT))

    def test_policy_is_recorded_in_the_result(self, case: Case, registry: LegalRuleRegistry):
        policy = EvaluationPolicy(satisfaction_threshold=0.4)
        evaluation = RuleEngine(registry, policy).evaluate_case(case, [])
        assert evaluation.policy.satisfaction_threshold == 0.4

    def test_evaluation_is_reproducible(self, engine: RuleEngine, case: Case):
        bindings = [
            binding("RULE_A", "C1", fact_ids=["F1"]),
            binding("RULE_A", "C2", BindingStance.CONTRADICTS, evidence_ids=["EV1"]),
        ]
        first = engine.evaluate_case(case, bindings)
        second = engine.evaluate_case(case, bindings)
        assert first.model_dump() == second.model_dump()


class TestConflictDetection:
    """Evidence rule E004 - contradictions must be surfaced"""

    def test_fact_supported_and_contradicted_is_reported(self, engine: RuleEngine, case: Case):
        conflicts = engine.detect_conflicts(case)
        fact_conflicts = [c for c in conflicts if c["type"] == "fact_conflict"]
        assert [c["fact_id"] for c in fact_conflicts] == ["F2"]
        assert fact_conflicts[0]["supporting_evidence"] == ["EV2"]
        assert fact_conflicts[0]["contradicting_evidence"] == ["EV3"]

    def test_disputed_conditions_are_reported(self, engine: RuleEngine, case: Case):
        evaluation = engine.evaluate_case(
            case,
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C1", BindingStance.CONTRADICTS, fact_ids=["F2"]),
            ],
        )
        condition_conflicts = [
            c for c in evaluation.conflicting_evidence if c["type"] == "condition_conflict"
        ]
        assert condition_conflicts
        assert condition_conflicts[0]["condition_id"] == "C1"
        assert condition_conflicts[0]["subject"] == SUBJECT

    def test_established_fact_contradicted_by_evidence_is_reported(
        self, engine: RuleEngine, case: Case
    ):
        # F3 becomes an established fact that only contradicting evidence speaks to
        case.facts[2].status = FactStatus.ESTABLISHED
        case.evidence[2].contradicts = ["F3"]
        conflicts = engine.detect_conflicts(case)
        reported = [c for c in conflicts if c["type"] == "contradicted_established_fact"]
        assert [c["fact_id"] for c in reported] == ["F3"]
        assert reported[0]["contradicting_evidence"] == ["EV3"]
