"""Court workflows

- ``run_judge_only`` (Phase 3): Case -> Judge -> Decision
- ``run_evidence_analysis`` (Phase 5): Case -> Evidence Agent
- ``run_adversarial_trial`` (Phases 4-5): Evidence -> Prosecution <-> Defense
  -> Judge

The full LangGraph court procedure is a later phase.
"""

from .adversarial import (
    DEFAULT_DEBATE_STAGES,
    QUICK_DEBATE_STAGES,
    TrialRun,
    check_stages,
    run_adversarial_trial,
)
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
    "EvidenceRun",
    "run_evidence_analysis",
    "JudgeOnlyRun",
    "run_judge_only",
]
