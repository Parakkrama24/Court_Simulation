"""Cases and the legal rules of the jurisdiction (read-only)"""

from typing import List

from fastapi import APIRouter, HTTPException

from app.agents.evidence import trace_case_provenance
from app.rules import LegalRuleRegistry, RuleEngine
from app.seed import get_all_cases, get_bindings_for_case, get_case_by_id

from ..schemas import CaseDetail, CaseSummary, RuleDetail

router = APIRouter(tags=["cases"])


def _summary(case) -> CaseSummary:  # type: ignore[no-untyped-def]
    return CaseSummary(
        case_id=case.case_id,
        title=case.title,
        defendant=case.defendant,
        charges=list(case.charges),
        case_type=case.case_type.value,
        jurisdiction=case.jurisdiction,
        facts=len(case.facts),
        evidence=len(case.evidence),
        witnesses=len(case.witnesses),
        applicable_laws=list(case.applicable_laws),
        runnable=bool(get_bindings_for_case(case.case_id)),
    )


@router.get("/cases", response_model=List[CaseSummary], summary="List the seeded cases")
def list_cases() -> List[CaseSummary]:
    return [_summary(case) for case in get_all_cases()]


@router.get(
    "/cases/{case_id}",
    response_model=CaseDetail,
    summary="One case: the record, the rule engine's evaluation, and evidence provenance",
    responses={404: {"description": "No such case"}},
)
def get_case(case_id: str) -> CaseDetail:
    case = get_case_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Unknown case '{case_id}'")

    registry = LegalRuleRegistry()
    bindings = get_bindings_for_case(case_id)
    evaluation = RuleEngine(registry).evaluate_case(case, bindings)
    return CaseDetail(
        case=case.model_dump(mode="json"),
        rule_evaluation=evaluation.model_dump(mode="json"),
        evidence_provenance=[p.model_dump(mode="json") for p in trace_case_provenance(case)],
        bindings=len(bindings),
        runnable=bool(bindings),
    )


@router.get("/rules", response_model=List[RuleDetail], summary="The legal rules of Arandia")
def list_rules() -> List[RuleDetail]:
    return [_rule(rule) for rule in LegalRuleRegistry()]


@router.get(
    "/rules/{rule_id}",
    response_model=RuleDetail,
    summary="One legal rule",
    responses={404: {"description": "No such rule"}},
)
def get_rule(rule_id: str) -> RuleDetail:
    rule = LegalRuleRegistry().get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Unknown legal rule '{rule_id}'")
    return _rule(rule)


def _rule(rule) -> RuleDetail:  # type: ignore[no-untyped-def]
    return RuleDetail(
        rule_id=rule.rule_id,
        name=rule.name,
        category=rule.category.value,
        description=rule.description,
        conditions=[c.model_dump(mode="json") for c in rule.conditions],
        effect=rule.effect,
        jurisdiction=rule.jurisdiction,
    )
