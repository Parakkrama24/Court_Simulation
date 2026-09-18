"""Legal rule engine for the Court Simulation System

Deterministic evaluation of structured legal rules against a case record,
plus the reference validator that keeps agent output grounded in real IDs.
"""

from .engine import CASE_WIDE_SUBJECT, RuleEngine
from .evaluator import ConditionEvaluator, assess_witness_reliability
from .models import (
    DEFAULT_POLICY,
    CaseEvaluation,
    ConditionEvaluation,
    ConditionStatus,
    EvaluationPolicy,
    ReferenceWeight,
    RuleEvaluation,
    RuleStatus,
    WitnessAssessment,
)
from .registry import LegalRuleRegistry, get_default_registry
from .validator import (
    ReferenceType,
    ReferenceValidator,
    ValidationError,
    ValidationResult,
)

__all__ = [
    "CASE_WIDE_SUBJECT",
    "RuleEngine",
    "ConditionEvaluator",
    "assess_witness_reliability",
    "DEFAULT_POLICY",
    "CaseEvaluation",
    "ConditionEvaluation",
    "ConditionStatus",
    "EvaluationPolicy",
    "ReferenceWeight",
    "RuleEvaluation",
    "RuleStatus",
    "WitnessAssessment",
    "LegalRuleRegistry",
    "get_default_registry",
    "ReferenceType",
    "ReferenceValidator",
    "ValidationError",
    "ValidationResult",
]
