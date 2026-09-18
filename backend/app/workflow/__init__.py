"""Court workflows

- ``run_judge_only`` (Phase 3): Case -> Judge -> Decision
- ``run_adversarial_trial`` (Phase 4): Prosecution <-> Defense -> Judge

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
from .judge_only import JudgeOnlyRun, run_judge_only

__all__ = [
    "DEFAULT_DEBATE_STAGES",
    "QUICK_DEBATE_STAGES",
    "TrialRun",
    "check_stages",
    "run_adversarial_trial",
    "WorkflowError",
    "JudgeOnlyRun",
    "run_judge_only",
]
