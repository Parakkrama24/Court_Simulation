"""Court workflows

- ``run_judge_only`` (Phase 3): Case -> Judge -> Decision
- ``run_evidence_analysis`` (Phase 5): Case -> Evidence Agent
- ``run_adversarial_trial`` (Phases 4-7): Evidence -> Prosecution <-> Defense
  -> Jury -> Judge -> Audit
- ``audit_trial`` (Phase 7): audit a finished or saved trial

The full LangGraph court procedure is a later phase.
"""

from .adversarial import (
    DEFAULT_DEBATE_STAGES,
    QUICK_DEBATE_STAGES,
    TrialRun,
    check_stages,
    run_adversarial_trial,
)
from .audit import audit_trial, build_dossier, deterministic_findings
from .common import WorkflowError
from .evidence_only import EvidenceRun, run_evidence_analysis
from .judge_only import JudgeOnlyRun, run_judge_only

__all__ = [
    "DEFAULT_DEBATE_STAGES",
    "QUICK_DEBATE_STAGES",
    "TrialRun",
    "check_stages",
    "run_adversarial_trial",
    "WorkflowError",
    "audit_trial",
    "build_dossier",
    "deterministic_findings",
    "EvidenceRun",
    "run_evidence_analysis",
    "JudgeOnlyRun",
    "run_judge_only",
]
