"""Result and policy models for the legal rule engine

These models describe the *output* of deterministic rule evaluation.
They are deliberately explicit: every conclusion carries the evidence and
facts it was derived from, so a later agent, auditor, or UI can show the
chain FACTS -> EVIDENCE -> CONDITION -> RULE without re-deriving it.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.domain import EvidenceType, FactStatus


# ============================================================================
# Enumerations
# ============================================================================


class ConditionStatus(str, Enum):
    """Outcome of evaluating a single condition of a legal rule"""

    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    DISPUTED = "disputed"
    UNSUPPORTED = "unsupported"


class RuleStatus(str, Enum):
    """Outcome of evaluating a complete legal rule"""

    SATISFIED = "satisfied"
    NOT_SATISFIED = "not_satisfied"
    INDETERMINATE = "indeterminate"
    UNCONDITIONAL = "unconditional"


# ============================================================================
# Evaluation Policy
# ============================================================================


class EvaluationPolicy(BaseModel):
    """Tunable, explicit weighting rules used by the engine

    The policy is data, not code, so experiments can vary how strictly the
    engine treats disputed facts or low-reliability evidence without touching
    the evaluation logic.
    """

    fact_weights: Dict[FactStatus, float] = Field(
        default_factory=lambda: {
            FactStatus.ESTABLISHED: 1.0,
            FactStatus.DISPUTED: 0.5,
            FactStatus.UNKNOWN: 0.25,
        },
        description="Weight contributed by a fact, by its status",
    )
    evidence_type_factors: Dict[EvidenceType, float] = Field(
        default_factory=lambda: {
            EvidenceType.PHYSICAL: 1.0,
            EvidenceType.FORENSIC: 1.0,
            EvidenceType.DOCUMENTARY: 1.0,
            EvidenceType.DIGITAL: 1.0,
            EvidenceType.TESTIMONIAL: 0.85,
            EvidenceType.CIRCUMSTANTIAL: 0.7,
        },
        description="Multiplier applied to evidence reliability, by evidence type",
    )
    satisfaction_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Support strength at or above which a condition may be satisfied",
    )
    dispute_threshold: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Contradiction strength at or above which a condition is contested",
    )

    model_config = ConfigDict(use_enum_values=False)


DEFAULT_POLICY = EvaluationPolicy()


# ============================================================================
# Evaluation Results
# ============================================================================


class ReferenceWeight(BaseModel):
    """The weight a single fact or evidence item contributed to a condition"""

    reference_id: str = Field(..., description="Fact or evidence ID")
    reference_type: str = Field(..., description="'fact' or 'evidence'")
    weight: float = Field(..., ge=0.0, le=1.0, description="Computed weight of this reference")
    explanation: str = Field(..., description="How the weight was derived")


class ConditionEvaluation(BaseModel):
    """Result of evaluating one condition of a legal rule"""

    rule_id: str = Field(..., description="Rule the condition belongs to")
    condition_id: str = Field(..., description="Condition identifier")
    description: str = Field(..., description="Condition text from the rule")
    required: bool = Field(default=True, description="Whether the condition is required")
    status: ConditionStatus = Field(..., description="Evaluated status of the condition")
    support_strength: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Strength of the supporting material"
    )
    contradiction_strength: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Strength of the contradicting material"
    )
    supporting_fact_ids: List[str] = Field(default_factory=list)
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_fact_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    weights: List[ReferenceWeight] = Field(
        default_factory=list, description="Per-reference weight breakdown"
    )
    depends_on_rule: Optional[str] = Field(
        default=None, description="Rule that determined this condition, if any"
    )
    reasoning: str = Field(default="", description="Deterministic explanation of the status")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Findings carried up from a dependency evaluation"
    )

    @property
    def is_satisfied(self) -> bool:
        return self.status == ConditionStatus.SATISFIED


class RuleEvaluation(BaseModel):
    """Result of evaluating a complete legal rule against a case"""

    rule_id: str = Field(..., description="Rule that was evaluated")
    rule_name: str = Field(..., description="Human-readable rule name")
    category: str = Field(..., description="Rule category")
    subject: str = Field(..., description="Party whose conduct was evaluated")
    status: RuleStatus = Field(..., description="Evaluated status of the rule")
    effect: str = Field(..., description="Effect declared by the rule")
    effect_applies: bool = Field(
        default=False, description="Whether the rule's effect is triggered by this evaluation"
    )
    conditions: List[ConditionEvaluation] = Field(default_factory=list)
    satisfied_conditions: List[str] = Field(default_factory=list)
    unsatisfied_conditions: List[str] = Field(default_factory=list)
    disputed_conditions: List[str] = Field(default_factory=list)
    unsupported_conditions: List[str] = Field(default_factory=list)
    reasoning: str = Field(default="", description="Deterministic explanation of the status")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def evidence_ids(self) -> List[str]:
        """All evidence IDs relied upon across conditions, in first-seen order"""
        seen: List[str] = []
        for condition in self.conditions:
            for eid in condition.supporting_evidence_ids + condition.contradicting_evidence_ids:
                if eid not in seen:
                    seen.append(eid)
        return seen

    @property
    def fact_ids(self) -> List[str]:
        """All fact IDs relied upon across conditions, in first-seen order"""
        seen: List[str] = []
        for condition in self.conditions:
            for fid in condition.supporting_fact_ids + condition.contradicting_fact_ids:
                if fid not in seen:
                    seen.append(fid)
        return seen


class WitnessAssessment(BaseModel):
    """Deterministic reliability assessment of a witness under rule E003"""

    witness_id: str = Field(..., description="Witness being assessed")
    name: str = Field(..., description="Witness name")
    reliability_score: float = Field(..., ge=0.0, le=1.0, description="Computed reliability score")
    positive_factors: List[str] = Field(
        default_factory=list, description="Factors increasing reliability"
    )
    challenge_grounds: List[str] = Field(
        default_factory=list, description="Factors that may be used to challenge the testimony"
    )
    unscored_factors: List[str] = Field(
        default_factory=list, description="Declared factors with no scoring rule"
    )
    reasoning: str = Field(default="", description="Explanation of the score")


class CaseEvaluation(BaseModel):
    """All rule evaluations for a case, plus the case-level summary"""

    case_id: str = Field(..., description="Case that was evaluated")
    rule_evaluations: List[RuleEvaluation] = Field(default_factory=list)
    witness_assessments: List[WitnessAssessment] = Field(default_factory=list)
    unevaluated_rules: List[str] = Field(
        default_factory=list, description="Applicable rules with no bindings for any subject"
    )
    conflicting_evidence: List[Dict[str, Any]] = Field(
        default_factory=list, description="Contradictions detected in the case record (rule E004)"
    )
    policy: EvaluationPolicy = Field(default_factory=EvaluationPolicy)

    def for_rule(self, rule_id: str, subject: Optional[str] = None) -> List[RuleEvaluation]:
        """Evaluations for a rule, optionally narrowed to one subject"""
        return [
            evaluation
            for evaluation in self.rule_evaluations
            if evaluation.rule_id == rule_id and (subject is None or evaluation.subject == subject)
        ]

    def for_subject(self, subject: str) -> List[RuleEvaluation]:
        """All rule evaluations concerning one party"""
        return [e for e in self.rule_evaluations if e.subject == subject]

    @property
    def applied_effects(self) -> List[str]:
        """Effects triggered by rules that were satisfied"""
        return [e.effect for e in self.rule_evaluations if e.effect_applies]
