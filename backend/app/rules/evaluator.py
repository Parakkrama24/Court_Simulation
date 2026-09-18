"""Condition evaluation

Turns the material bound to a legal condition (facts and evidence) into a
deterministic condition status. No LLM is involved: the same case and the
same bindings always produce the same result.

Weighting model
---------------
Each referenced fact contributes a weight based on its status, and each
referenced evidence item contributes ``reliability * type_factor``. A
condition's support (or contradiction) strength is the *strongest* single
reference on that side - one reliable item can carry an element, and adding
weak duplicates never manufactures certainty.

Status is then decided by two thresholds from the policy - whether support
reaches ``satisfaction_threshold``, and whether contradiction reaches
``dispute_threshold``:

    supported + contested      -> DISPUTED
    supported, not contested   -> SATISFIED
    contested, not supported   -> UNSATISFIED
    neither                    -> UNSUPPORTED
"""

from typing import Dict, List, Optional, Sequence, Tuple

from app.domain import BindingStance, Case, ElementBinding, Evidence, Fact, Witness

from .models import (
    DEFAULT_POLICY,
    ConditionEvaluation,
    ConditionStatus,
    EvaluationPolicy,
    ReferenceWeight,
    WitnessAssessment,
)


_STATUS_HEADLINES = {
    ConditionStatus.SATISFIED: (
        "Supported by sufficiently strong material with no substantial contradiction"
    ),
    ConditionStatus.DISPUTED: (
        "Supported, but substantial contradicting material remains unresolved"
    ),
    ConditionStatus.UNSATISFIED: (
        "Contradicted, without sufficiently strong supporting material"
    ),
    ConditionStatus.UNSUPPORTED: "No sufficiently strong material bears on this condition",
}


class ConditionEvaluator:
    """Evaluates individual legal conditions against a case record"""

    def __init__(self, case: Case, policy: Optional[EvaluationPolicy] = None) -> None:
        self.case = case
        self.policy = policy or DEFAULT_POLICY
        self._facts: Dict[str, Fact] = {fact.fact_id: fact for fact in case.facts}
        self._evidence: Dict[str, Evidence] = {item.evidence_id: item for item in case.evidence}

    # ------------------------------------------------------------------
    # Weights
    # ------------------------------------------------------------------

    def fact_weight(self, fact: Fact) -> ReferenceWeight:
        """Weight contributed by a fact, based on its status"""
        weight = self.policy.fact_weights.get(fact.status, 0.0)
        return ReferenceWeight(
            reference_id=fact.fact_id,
            reference_type="fact",
            weight=weight,
            explanation=f"fact status '{fact.status.value}' weighted {weight:.2f}",
        )

    def evidence_weight(self, evidence: Evidence) -> ReferenceWeight:
        """Weight contributed by evidence: reliability scaled by evidence type"""
        factor = self.policy.evidence_type_factors.get(evidence.type, 1.0)
        weight = evidence.reliability * factor
        return ReferenceWeight(
            reference_id=evidence.evidence_id,
            reference_type="evidence",
            weight=weight,
            explanation=(
                f"reliability {evidence.reliability:.2f} x "
                f"{evidence.type.value} factor {factor:.2f} = {weight:.2f}"
            ),
        )

    # ------------------------------------------------------------------
    # Condition evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        rule_id: str,
        condition_id: str,
        description: str,
        bindings: Sequence[ElementBinding],
        required: bool = True,
    ) -> ConditionEvaluation:
        """Evaluate one condition from the bindings that reference it"""
        supporting = [b for b in bindings if b.stance == BindingStance.SUPPORTS]
        contradicting = [b for b in bindings if b.stance == BindingStance.CONTRADICTS]

        support_facts, support_evidence, support_weights = self._collect(supporting)
        contra_facts, contra_evidence, contra_weights = self._collect(contradicting)

        support_strength = max((w.weight for w in support_weights), default=0.0)
        contradiction_strength = max((w.weight for w in contra_weights), default=0.0)

        supported = support_strength >= self.policy.satisfaction_threshold
        contested = contradiction_strength >= self.policy.dispute_threshold

        if supported and contested:
            status = ConditionStatus.DISPUTED
        elif supported:
            status = ConditionStatus.SATISFIED
        elif contested:
            status = ConditionStatus.UNSATISFIED
        else:
            status = ConditionStatus.UNSUPPORTED

        return ConditionEvaluation(
            rule_id=rule_id,
            condition_id=condition_id,
            description=description,
            required=required,
            status=status,
            support_strength=support_strength,
            contradiction_strength=contradiction_strength,
            supporting_fact_ids=support_facts,
            supporting_evidence_ids=support_evidence,
            contradicting_fact_ids=contra_facts,
            contradicting_evidence_ids=contra_evidence,
            weights=support_weights + contra_weights,
            reasoning=self._explain(status, support_strength, contradiction_strength),
        )

    def _collect(
        self, bindings: Sequence[ElementBinding]
    ) -> Tuple[List[str], List[str], List[ReferenceWeight]]:
        """Resolve binding references into de-duplicated IDs and their weights"""
        fact_ids: List[str] = []
        evidence_ids: List[str] = []
        weights: List[ReferenceWeight] = []

        for binding in bindings:
            for fact_id in binding.fact_ids:
                fact = self._facts.get(fact_id)
                if fact is None or fact_id in fact_ids:
                    continue
                fact_ids.append(fact_id)
                weights.append(self.fact_weight(fact))
            for evidence_id in binding.evidence_ids:
                evidence = self._evidence.get(evidence_id)
                if evidence is None or evidence_id in evidence_ids:
                    continue
                evidence_ids.append(evidence_id)
                weights.append(self.evidence_weight(evidence))

        return fact_ids, evidence_ids, weights

    def _explain(self, status: ConditionStatus, support: float, contradiction: float) -> str:
        """Human-readable justification for a condition status"""
        thresholds = (
            f"support {support:.2f} (threshold {self.policy.satisfaction_threshold:.2f}), "
            f"contradiction {contradiction:.2f} (threshold {self.policy.dispute_threshold:.2f})"
        )
        headline = _STATUS_HEADLINES[status]
        return f"{headline}: {thresholds}."


# ============================================================================
# Witness reliability (rule E003)
# ============================================================================

# Each entry maps a declared reliability factor to (penalty, challenge_ground).
# Matching is by substring on the normalised factor value, first match wins,
# so more specific values must be listed before less specific ones.
_FACTOR_RULES: Dict[str, List[Tuple[str, float, Optional[str]]]] = {
    "opportunity_to_observe": [
        ("high", 0.0, None),
        ("moderate", 0.05, None),
        ("low", 0.20, "limited opportunity to observe"),
        ("none", 0.30, "no opportunity to observe"),
    ],
    "bias": [
        ("none", 0.0, None),
        ("no_bias", 0.0, None),
    ],
    "memory_quality": [
        ("impair", 0.20, "memory may be impaired"),
        ("poor", 0.20, "poor memory"),
        ("moderate", 0.10, None),
        ("fair", 0.10, None),
        ("good", 0.0, None),
        ("excellent", 0.0, None),
    ],
    "consistency": [
        ("conflict", 0.25, "testimony conflicts with other evidence"),
        ("inconsist", 0.25, "testimony is internally inconsistent"),
        ("consistent", 0.0, None),
    ],
    "personal_interest": [
        ("very_high", 0.20, "very high personal interest in the outcome"),
        ("high", 0.15, "high personal interest in the outcome"),
        ("moderate", 0.05, None),
        ("none", 0.0, None),
        ("low", 0.0, None),
    ],
}

# Bias is scored by exception: any value other than "none"/"no_bias" is a
# challenge ground, because the specific bias text varies by case.
_BIAS_PENALTY = 0.20


def assess_witness_reliability(witness: Witness) -> WitnessAssessment:
    """Score a witness deterministically from declared reliability factors

    Implements evidence rule E003: testimony may be challenged on the grounds
    of bias, memory limitations, consistency, opportunity to observe, and
    personal interest. The score starts at 1.0 and each adverse factor
    subtracts a fixed, documented penalty.
    """
    score = 1.0
    positives: List[str] = []
    challenges: List[str] = []
    unscored: List[str] = []

    for factor, raw_value in witness.reliability_factors.items():
        value = str(raw_value).strip().lower()

        if factor == "bias":
            if value in {"none", "none_apparent", "no_bias", "no_apparent_bias"}:
                positives.append("no apparent bias")
            else:
                score -= _BIAS_PENALTY
                challenges.append(f"bias: {value}")
            continue

        rules = _FACTOR_RULES.get(factor)
        if rules is None:
            unscored.append(f"{factor}: {value}")
            continue

        for token, penalty, challenge in rules:
            if token in value:
                score -= penalty
                if challenge:
                    challenges.append(challenge)
                elif penalty == 0.0:
                    positives.append(f"{factor}: {value}")
                break
        else:
            unscored.append(f"{factor}: {value}")

    score = round(max(0.0, min(1.0, score)), 4)
    if challenges:
        reasoning = (
            f"Reliability reduced to {score:.2f} by {len(challenges)} challenge ground(s): "
            + "; ".join(challenges)
        )
    else:
        reasoning = f"No challenge grounds identified; reliability {score:.2f}"

    return WitnessAssessment(
        witness_id=witness.witness_id,
        name=witness.name,
        reliability_score=score,
        positive_factors=positives,
        challenge_grounds=challenges,
        unscored_factors=unscored,
        reasoning=reasoning,
    )
