"""Jury agents and the verdict engine"""

from .agent import JurorAgent, JurorAgentError, JurorDecision
from .aggregation import (
    ChargeTally,
    JuryOutcome,
    JuryResult,
    JuryRule,
    VoteChange,
    aggregate_jury,
    judge_jury_agreement,
    jury_context,
    tally_votes,
)
from .prompts import PROMPT_VERSION, build_system_prompt
from .schema import JurorChargeVerdict, JurorDeliberationOutput, JurorVerdictOutput
from .validation import JurorOutputValidator, JurorValidationReport


__all__ = [
    "JurorAgent",
    "JurorAgentError",
    "JurorDecision",
    "ChargeTally",
    "JuryOutcome",
    "JuryResult",
    "JuryRule",
    "VoteChange",
    "aggregate_jury",
    "judge_jury_agreement",
    "tally_votes",
    "PROMPT_VERSION",
    "build_system_prompt",
    "JurorChargeVerdict",
    "JurorDeliberationOutput",
    "JurorVerdictOutput",
    "JurorOutputValidator",
    "JurorValidationReport",
    "jury_context",
]
