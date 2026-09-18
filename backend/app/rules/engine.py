"""Legal rule engine

Evaluates structured legal rules against a case record. The engine is the
authority on whether a legal element holds: agents may propose which facts and
evidence bear on an element (bindings), but the conclusion is computed here,
deterministically, from the case record alone.

    Facts + Evidence --(bindings)--> Conditions --> Rule status --> Effects
"""

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from app.domain import Case, Condition, ElementBinding, FactStatus, LegalCategory, LegalRule

from .evaluator import ConditionEvaluator, assess_witness_reliability
from .models import (
    DEFAULT_POLICY,
    CaseEvaluation,
    ConditionEvaluation,
    ConditionStatus,
    EvaluationPolicy,
    RuleEvaluation,
    RuleStatus,
)
from .registry import LegalRuleRegistry

# Subject used for rules that apply to the proceeding rather than to the
# conduct of a particular party (principles, evidence rules).
CASE_WIDE_SUBJECT = "case"



# Condition statuses whose supporting / contradicting references are carried
# up into a condition that depends on the rule.
_SUPPORTING = (ConditionStatus.SATISFIED, ConditionStatus.DISPUTED)
_OPPOSING = (ConditionStatus.UNSATISFIED, ConditionStatus.DISPUTED)


def _collect_ids(
    conditions: Sequence[ConditionEvaluation],
    attribute: str,
    statuses: Tuple[ConditionStatus, ...],
) -> List[str]:
    """De-duplicated IDs from the conditions whose status is in `statuses`"""
    collected: List[str] = []
    for condition in conditions:
        if condition.status not in statuses:
            continue
        for reference_id in getattr(condition, attribute):
            if reference_id not in collected:
                collected.append(reference_id)
    return collected


class RuleEngine:
    """Deterministic evaluator for structured legal rules"""

    def __init__(
        self,
        registry: Optional[LegalRuleRegistry] = None,
        policy: Optional[EvaluationPolicy] = None,
    ) -> None:
        self.registry = registry or LegalRuleRegistry()
        self.policy = policy or DEFAULT_POLICY

    # ------------------------------------------------------------------
    # Single rule
    # ------------------------------------------------------------------

    def evaluate_rule(
        self,
        case: Case,
        rule_id: str,
        subject: str,
        bindings: Sequence[ElementBinding],
    ) -> RuleEvaluation:
        """Evaluate one rule against the case for one subject"""
        return self._evaluate_rule(case, rule_id, subject, bindings, stack=())

    def _evaluate_rule(
        self,
        case: Case,
        rule_id: str,
        subject: str,
        bindings: Sequence[ElementBinding],
        stack: Tuple[Tuple[str, str], ...],
    ) -> RuleEvaluation:
        rule = self.registry.require(rule_id)
        evaluator = ConditionEvaluator(case, self.policy)
        relevant = [b for b in bindings if b.rule_id == rule_id and b.subject == subject]

        condition_evaluations = [
            self._evaluate_condition(
                case=case,
                evaluator=evaluator,
                rule=rule,
                condition=condition,
                subject=subject,
                bindings=bindings,
                relevant=relevant,
                stack=stack + ((rule_id, subject),),
            )
            for condition in rule.conditions
        ]

        return self._build_evaluation(rule, subject, condition_evaluations)

    def _evaluate_condition(
        self,
        case: Case,
        evaluator: ConditionEvaluator,
        rule: LegalRule,
        condition: Condition,
        subject: str,
        bindings: Sequence[ElementBinding],
        relevant: Sequence[ElementBinding],
        stack: Tuple[Tuple[str, str], ...],
    ) -> ConditionEvaluation:
        """Evaluate one condition, resolving a rule dependency if declared"""
        if condition.depends_on_rule:
            return self._condition_from_dependency(
                case=case,
                rule=rule,
                condition=condition,
                subject=subject,
                bindings=bindings,
                stack=stack,
            )

        condition_bindings = [b for b in relevant if b.condition_id == condition.id]
        return evaluator.evaluate(
            rule_id=rule.rule_id,
            condition_id=condition.id,
            description=condition.description,
            bindings=condition_bindings,
            required=condition.required,
        )

    def _condition_from_dependency(
        self,
        case: Case,
        rule: LegalRule,
        condition: Condition,
        subject: str,
        bindings: Sequence[ElementBinding],
        stack: Tuple[Tuple[str, str], ...],
    ) -> ConditionEvaluation:
        """Derive a condition's status from another rule's evaluation"""
        dependency_id = str(condition.depends_on_rule)
        base = ConditionEvaluation(
            rule_id=rule.rule_id,
            condition_id=condition.id,
            description=condition.description,
            required=condition.required,
            status=ConditionStatus.UNSUPPORTED,
            depends_on_rule=dependency_id,
        )

        if (dependency_id, subject) in stack:
            base.reasoning = (
                f"Circular dependency detected: {dependency_id} is already being evaluated "
                f"for {subject}; condition left unsupported."
            )
            base.metadata["circular_dependency"] = True
            return base

        if dependency_id not in self.registry:
            base.reasoning = f"Condition depends on unknown rule {dependency_id}."
            return base

        dependency = self._evaluate_rule(case, dependency_id, subject, bindings, stack)

        status_map = {
            RuleStatus.SATISFIED: ConditionStatus.SATISFIED,
            RuleStatus.UNCONDITIONAL: ConditionStatus.SATISFIED,
            RuleStatus.NOT_SATISFIED: ConditionStatus.UNSATISFIED,
            RuleStatus.INDETERMINATE: ConditionStatus.DISPUTED,
        }
        status = status_map[dependency.status]
        if status == ConditionStatus.DISPUTED and not dependency.conditions:
            status = ConditionStatus.UNSUPPORTED

        # A derived condition is only as strong as the weakest element of the
        # rule it depends on, and inherits that rule's strongest contradiction.
        decisive = [c for c in dependency.conditions if c.required] or dependency.conditions
        base.status = status
        base.support_strength = min((c.support_strength for c in decisive), default=1.0)
        base.contradiction_strength = max((c.contradiction_strength for c in decisive), default=0.0)
        base.supporting_fact_ids = _collect_ids(decisive, "supporting_fact_ids", _SUPPORTING)
        base.supporting_evidence_ids = _collect_ids(
            decisive, "supporting_evidence_ids", _SUPPORTING
        )
        base.contradicting_fact_ids = _collect_ids(decisive, "contradicting_fact_ids", _OPPOSING)
        base.contradicting_evidence_ids = _collect_ids(
            decisive, "contradicting_evidence_ids", _OPPOSING
        )
        base.reasoning = (
            f"Determined by rule {dependency_id} ({dependency.rule_name}), "
            f"evaluated as '{dependency.status.value}' for {subject}."
        )
        base.metadata["dependency_status"] = dependency.status.value

        # A cycle broken further down the chain still explains why this
        # condition could not be resolved, so carry the finding up.
        if any(c.metadata.get("circular_dependency") for c in dependency.conditions):
            base.metadata["circular_dependency"] = True
            base.reasoning += (
                f" Rule {dependency_id} could not be resolved because of a circular "
                "dependency between legal rules."
            )
        return base

    def _build_evaluation(
        self,
        rule: LegalRule,
        subject: str,
        conditions: List[ConditionEvaluation],
    ) -> RuleEvaluation:
        """Aggregate condition results into a rule status"""
        def ids(status: ConditionStatus) -> List[str]:
            return [c.condition_id for c in conditions if c.status == status]

        satisfied = ids(ConditionStatus.SATISFIED)
        unsatisfied = ids(ConditionStatus.UNSATISFIED)
        disputed = ids(ConditionStatus.DISPUTED)
        unsupported = ids(ConditionStatus.UNSUPPORTED)

        if not conditions:
            status = RuleStatus.UNCONDITIONAL
            reasoning = "Rule states no conditions; its effect applies to the proceeding."
        else:
            # Optional conditions (e.g. witness reliability factors) only decide
            # the rule when a rule states no required conditions at all.
            decisive = [c for c in conditions if c.required] or conditions
            blocked = [c.condition_id for c in decisive if c.status == ConditionStatus.UNSATISFIED]
            open_items = [
                c.condition_id
                for c in decisive
                if c.status in (ConditionStatus.DISPUTED, ConditionStatus.UNSUPPORTED)
            ]

            if blocked:
                status = RuleStatus.NOT_SATISFIED
                reasoning = f"Condition(s) {', '.join(blocked)} are contradicted by the record."
            elif open_items:
                status = RuleStatus.INDETERMINATE
                reasoning = (
                    f"Condition(s) {', '.join(open_items)} remain disputed or unsupported; "
                    "the rule can be neither applied nor excluded on this record."
                )
            else:
                status = RuleStatus.SATISFIED
                reasoning = "All required conditions are supported by the case record."

        effect_applies = status in (RuleStatus.SATISFIED, RuleStatus.UNCONDITIONAL)

        return RuleEvaluation(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            category=rule.category.value,
            subject=subject,
            status=status,
            effect=rule.effect,
            effect_applies=effect_applies,
            conditions=conditions,
            satisfied_conditions=satisfied,
            unsatisfied_conditions=unsatisfied,
            disputed_conditions=disputed,
            unsupported_conditions=unsupported,
            reasoning=reasoning,
            metadata=dict(rule.metadata),
        )

    # ------------------------------------------------------------------
    # Whole case
    # ------------------------------------------------------------------

    def evaluate_case(
        self,
        case: Case,
        bindings: Sequence[ElementBinding],
        rule_ids: Optional[Sequence[str]] = None,
        include_principles: bool = True,
    ) -> CaseEvaluation:
        """Evaluate every applicable rule against the case

        Rules with conditions are evaluated once per subject that has bindings.
        Rules without conditions (principles, and evidence rules that state a
        prohibition) apply case-wide.
        """
        case_bindings = [b for b in bindings if b.case_id == case.case_id]
        targets = list(rule_ids) if rule_ids is not None else list(case.applicable_laws)

        if include_principles:
            targets += [
                rule.rule_id
                for rule in self.registry.by_category(LegalCategory.PRINCIPLE)
                if rule.rule_id not in targets
            ]

        by_rule_subject: Dict[str, List[str]] = defaultdict(list)
        for binding in case_bindings:
            subjects = by_rule_subject[binding.rule_id]
            if binding.subject not in subjects:
                subjects.append(binding.subject)

        evaluations: List[RuleEvaluation] = []
        unevaluated: List[str] = []

        for rule_id in targets:
            rule = self.registry.get(rule_id)
            if rule is None:
                unevaluated.append(rule_id)
                continue

            if not rule.conditions:
                evaluations.append(
                    self._evaluate_rule(case, rule_id, CASE_WIDE_SUBJECT, case_bindings, stack=())
                )
                continue

            subjects = by_rule_subject.get(rule_id, [])
            if not subjects:
                unevaluated.append(rule_id)
                continue

            for subject in subjects:
                evaluations.append(
                    self._evaluate_rule(case, rule_id, subject, case_bindings, stack=())
                )

        return CaseEvaluation(
            case_id=case.case_id,
            rule_evaluations=evaluations,
            witness_assessments=[assess_witness_reliability(w) for w in case.witnesses],
            unevaluated_rules=unevaluated,
            conflicting_evidence=self.detect_conflicts(case, evaluations),
            policy=self.policy,
        )

    # ------------------------------------------------------------------
    # Conflicts (evidence rule E004)
    # ------------------------------------------------------------------

    def detect_conflicts(
        self,
        case: Case,
        evaluations: Optional[Sequence[RuleEvaluation]] = None,
    ) -> List[Dict[str, object]]:
        """Identify contradictions that must be explicitly addressed (E004)

        Two sources are reported: facts that evidence both supports and
        contradicts, and legal conditions whose supporting and contradicting
        material are both substantial.
        """
        conflicts: List[Dict[str, object]] = []

        for fact in case.facts:
            supporting = [e.evidence_id for e in case.evidence if fact.fact_id in e.supports]
            contradicting = [e.evidence_id for e in case.evidence if fact.fact_id in e.contradicts]
            if supporting and contradicting:
                conflicts.append(
                    {
                        "type": "fact_conflict",
                        "rule_id": "E004",
                        "fact_id": fact.fact_id,
                        "supporting_evidence": supporting,
                        "contradicting_evidence": contradicting,
                        "description": (
                            f"Evidence both supports and contradicts {fact.fact_id}: "
                            f"{fact.description}"
                        ),
                    }
                )
            elif contradicting and fact.status == FactStatus.ESTABLISHED:
                conflicts.append(
                    {
                        "type": "contradicted_established_fact",
                        "rule_id": "E004",
                        "fact_id": fact.fact_id,
                        "supporting_evidence": [],
                        "contradicting_evidence": contradicting,
                        "description": (
                            f"Fact {fact.fact_id} is recorded as established but is "
                            f"contradicted by evidence."
                        ),
                    }
                )

        for evaluation in evaluations or []:
            for condition in evaluation.conditions:
                if condition.status != ConditionStatus.DISPUTED:
                    continue
                conflicts.append(
                    {
                        "type": "condition_conflict",
                        "rule_id": evaluation.rule_id,
                        "condition_id": condition.condition_id,
                        "subject": evaluation.subject,
                        "supporting_evidence": list(condition.supporting_evidence_ids),
                        "contradicting_evidence": list(condition.contradicting_evidence_ids),
                        "description": (
                            f"{evaluation.rule_id} condition {condition.condition_id} "
                            f"({condition.description}) is contested for {evaluation.subject}."
                        ),
                    }
                )

        return conflicts
