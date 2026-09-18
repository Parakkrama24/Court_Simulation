"""Court simulation agents

Phase 3 implements the Judge Agent only. Prosecution, defense, evidence,
jury, and auditor agents arrive in later phases.
"""

from .judge import JudgeAgent, JudgeAgentError, JudgeResult

__all__ = ["JudgeAgent", "JudgeAgentError", "JudgeResult"]
