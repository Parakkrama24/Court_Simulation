"""Legal Process Auditor: inspects how the simulation ran, never the verdict"""

from .agent import (
    AUDITOR_AGENT_ID,
    MAX_AUDITOR_FINDINGS,
    AuditorAgent,
    AuditorAgentError,
    AuditorResult,
    AuditorValidator,
    ProcessAudit,
)
from .findings import (
    SEVERITY_ORDER,
    AuditCategory,
    AuditFinding,
    FindingSource,
    OverallStatus,
    Severity,
    build_audit_report,
    overall_status,
    severity_counts,
    summarise,
)
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT
from .schema import AuditorFinding, AuditorOutput, ChainAssessment, ChainLink, LinkRating

__all__ = [
    "AUDITOR_AGENT_ID",
    "MAX_AUDITOR_FINDINGS",
    "AuditorAgent",
    "AuditorAgentError",
    "AuditorResult",
    "AuditorValidator",
    "ProcessAudit",
    "SEVERITY_ORDER",
    "AuditCategory",
    "AuditFinding",
    "FindingSource",
    "OverallStatus",
    "Severity",
    "build_audit_report",
    "overall_status",
    "severity_counts",
    "summarise",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "AuditorFinding",
    "AuditorOutput",
    "ChainAssessment",
    "ChainLink",
    "LinkRating",
]
