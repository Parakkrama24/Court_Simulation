"""Court workflows

- ``run_judge_only`` (Phase 3): Case -> Judge -> Decision
- ``run_evidence_analysis`` (Phase 5): Case -> Evidence Agent
- ``run_court`` (Phase 8): the full spec section 14 procedure as a LangGraph
  state machine, with conditional transitions
- ``run_adversarial_trial`` (Phases 4-7): a linear runner for custom stage
  plans
- ``audit_trial`` (Phase 7): audit a finished or saved trial

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
from .graph import (
    CourtState,
    build_court_graph,
    court_graph_mermaid,
    initial_state,
    run_court,
    run_from_state,
)
from .steps import Court, CourtOptions, open_court
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
    "CourtState",
    "build_court_graph",
    "court_graph_mermaid",
    "initial_state",
    "run_court",
    "run_from_state",
    "Court",
    "CourtOptions",
    "open_court",
    "run_evidence_analysis",
    "JudgeOnlyRun",
    "run_judge_only",
]
