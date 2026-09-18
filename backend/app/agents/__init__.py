"""Court simulation agents

- Judge Agent (Phase 3): decides every charge from the record and arguments
- Prosecution and Defense agents (Phase 4): adversarial, evidence-grounded
  argument

Every agent runs through the same validated-generation loop (``base.py``):
output that cites anything outside the record is rejected and regenerated.
Evidence, jury, and auditor agents arrive in later phases.
"""

from .advocate import AdvocateAgent, AdvocateAgentError, AdvocateRole, AdvocateTurn
from .base import AgentAttempt, AgentError
from .judge import JudgeAgent, JudgeAgentError, JudgeResult

__all__ = [
    "AdvocateAgent",
    "AdvocateAgentError",
    "AdvocateRole",
    "AdvocateTurn",
    "AgentAttempt",
    "AgentError",
    "JudgeAgent",
    "JudgeAgentError",
    "JudgeResult",
]
