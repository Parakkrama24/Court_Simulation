"""Audit findings and report assembly

A finding is one problem with *how the simulation ran* - never a view on how
the case should have been decided. Findings come from two sources:

- ``deterministic`` - checks computed in code from the trial record
- ``auditor_agent`` - the LLM auditor's review of what code cannot judge

Both are assembled into the domain ``AuditReport``, with findings filed under
the report's five lists by category.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from app.domain import AuditReport


class AuditCategory(str, Enum):
    """Spec section 9's four integrity areas, plus hallucinations"""

    EVIDENCE = "evidence"
    LEGAL = "legal"
    REASONING = "reasoning"
    PROCEDURAL = "procedural"
    HALLUCINATION = "hallucination"


class Severity(str, Enum):
    """How much a finding undermines the simulation, in increasing order"""

    INFO = "info"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


SEVERITY_ORDER = [Severity.INFO, Severity.MINOR, Severity.MAJOR, Severity.CRITICAL]


class FindingSource(str, Enum):
    DETERMINISTIC = "deterministic"
    AUDITOR_AGENT = "auditor_agent"


class AuditFinding(BaseModel):
    """One problem with how the simulation ran"""

    finding_id: str
    category: AuditCategory
    severity: Severity
    check: str = Field(..., description="Machine-readable name of the check or issue type")
    agent_id: str = Field(default="", description="Agent responsible, if any")
    stage: str = Field(default="", description="Court stage, if any")
    description: str
    references: List[str] = Field(
        default_factory=list, description="Argument, message, or record IDs involved"
    )
    source: FindingSource


class OverallStatus(str, Enum):
    CLEAN = "clean"
    MINOR_ISSUES = "minor_issues"
    MAJOR_ISSUES = "major_issues"
    CRITICAL_ISSUES = "critical_issues"


_REPORT_FIELDS = {
    AuditCategory.EVIDENCE: "evidence_violations",
    AuditCategory.LEGAL: "legal_violations",
    AuditCategory.PROCEDURAL: "procedural_violations",
    AuditCategory.REASONING: "reasoning_issues",
    AuditCategory.HALLUCINATION: "hallucinations",
}


def overall_status(findings: Sequence[AuditFinding]) -> OverallStatus:
    """The worst severity present decides the overall status"""
    worst = max((SEVERITY_ORDER.index(f.severity) for f in findings), default=0)
    return [
        OverallStatus.CLEAN,  # info-only findings do not count against the run
        OverallStatus.MINOR_ISSUES,
        OverallStatus.MAJOR_ISSUES,
        OverallStatus.CRITICAL_ISSUES,
    ][worst]


def severity_counts(findings: Sequence[AuditFinding]) -> Dict[str, int]:
    return {s.value: sum(1 for f in findings if f.severity == s) for s in Severity}


def summarise(findings: Sequence[AuditFinding]) -> str:
    """A deterministic one-paragraph assessment, used when no auditor agent ran"""
    status = overall_status(findings)
    counts = severity_counts(findings)
    parts = [f"{counts[s.value]} {s.value}" for s in reversed(SEVERITY_ORDER) if counts[s.value]]
    tally = ", ".join(parts) if parts else "no findings"
    return f"Overall status: {status.value} ({tally})."


def build_audit_report(
    case_id: str,
    findings: Sequence[AuditFinding],
    final_assessment: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditReport:
    """File findings under the AuditReport's lists and summarise them"""
    lists: Dict[str, List[Dict[str, Any]]] = {name: [] for name in _REPORT_FIELDS.values()}
    for finding in findings:
        lists[_REPORT_FIELDS[finding.category]].append(finding.model_dump(mode="json"))

    status = overall_status(findings)
    return AuditReport(
        audit_id=f"AUD_{case_id}",
        case_id=case_id,
        final_assessment=final_assessment or summarise(findings),
        metadata={
            "overall_status": status.value,
            "severity_counts": severity_counts(findings),
            "sources": {
                source.value: sum(1 for f in findings if f.source == source)
                for source in FindingSource
            },
            **(metadata or {}),
        },
        **lists,
    )
