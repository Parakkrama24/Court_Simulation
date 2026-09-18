"""Court simulation agents

- Judge Agent (Phase 3): decides every charge from the record and arguments
- Prosecution and Defense agents (Phase 4): adversarial, evidence-grounded
  argument
- Evidence Agent (Phase 5): neutral evidence analysis and argument review
- Jury agents (Phase 6): independent verdicts, then controlled deliberation

Every agent runs through the same validated-generation loop (``base.py``):
output that cites anything outside the record is rejected and regenerated.
The auditor agent arrives in a later phase.
"""

from .advocate import AdvocateAgent, AdvocateAgentError, AdvocateRole, AdvocateTurn
from .base import AgentAttempt, AgentError
from .evidence import (
    EvidenceAgent,
    EvidenceAgentError,
    EvidenceAnalysis,
    EvidenceReview,
    evidence_context,
)
from .judge import JudgeAgent, JudgeAgentError, JudgeResult
from .jury import JurorAgent, JurorAgentError, JurorDecision, JuryResult, JuryRule

__all__ = [
    "AdvocateAgent",
    "AdvocateAgentError",
    "AdvocateRole",
    "AdvocateTurn",
    "AgentAttempt",
    "AgentError",
    "EvidenceAgent",
    "EvidenceAgentError",
    "EvidenceAnalysis",
    "EvidenceReview",
    "evidence_context",
    "JudgeAgent",
    "JudgeAgentError",
    "JudgeResult",
    "JurorAgent",
    "JurorAgentError",
    "JurorDecision",
    "JuryResult",
    "JuryRule",
]
