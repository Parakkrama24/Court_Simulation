"""Steps shared by every court workflow"""

from typing import Any, Dict, List, Tuple

from app.domain import Case, utc_now
from app.rules import CaseEvaluation, LegalRuleRegistry, ReferenceValidator, RuleEngine
from app.seed import get_bindings_for_case, get_case_by_id


class WorkflowError(Exception):
    """A workflow could not run to completion"""


def event(stage: str, event_type: str, **details: Any) -> Dict[str, Any]:
    """One structured entry for a run's event history"""
    return {
        "stage": stage,
        "event_type": event_type,
        "timestamp": utc_now().isoformat(),
        **details,
    }


def prepare_case(
    case_id: str, registry: LegalRuleRegistry, events: List[Dict[str, Any]]
) -> Tuple[Case, CaseEvaluation]:
    """CASE_INITIALIZATION and rule evaluation, recording both as events"""
    case = get_case_by_id(case_id)
    if case is None:
        raise WorkflowError(f"Unknown case '{case_id}'")
    events.append(
        event(
            "CASE_INITIALIZATION",
            "CASE_LOADED",
            case_id=case.case_id,
            facts=len(case.facts),
            evidence=len(case.evidence),
            witnesses=len(case.witnesses),
            charges=list(case.charges),
        )
    )

    # Re-validate the seeded bindings so a broken seed fails the run rather
    # than quietly skewing every agent's input.
    bindings = get_bindings_for_case(case.case_id)
    binding_check = ReferenceValidator(case, registry).validate_bindings(bindings)
    if not binding_check.valid:
        raise WorkflowError(
            f"Seeded bindings for {case.case_id} are invalid: {'; '.join(binding_check.messages)}"
        )

    evaluation = RuleEngine(registry).evaluate_case(case, bindings)
    events.append(
        event(
            "RULE_EVALUATION",
            "RULES_EVALUATED",
            bindings=len(bindings),
            rules={f"{r.rule_id}/{r.subject}": r.status.value for r in evaluation.rule_evaluations},
            unevaluated_rules=list(evaluation.unevaluated_rules),
        )
    )
    return case, evaluation
