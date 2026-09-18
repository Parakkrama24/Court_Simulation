"""Prosecution and Defense agents"""

from .agent import AdvocateAgent, AdvocateAgentError, AdvocateTurn
from .prompts import PROMPT_VERSION, build_system_prompt, build_user_prompt
from .roles import (
    REBUTTAL_STAGES,
    STAGE_CODES,
    STAGE_MESSAGE_TYPES,
    STAGE_SPEAKERS,
    AdvocateRole,
)
from .schema import AdvocateTurnOutput, ArgumentDraft, ElementRef
from .validation import (
    MAX_ARGUMENTS_PER_TURN,
    AdvocacyFlag,
    AdvocateTurnValidator,
    AdvocateValidationReport,
)

__all__ = [
    "AdvocateAgent",
    "AdvocateAgentError",
    "AdvocateTurn",
    "PROMPT_VERSION",
    "build_system_prompt",
    "build_user_prompt",
    "REBUTTAL_STAGES",
    "STAGE_CODES",
    "STAGE_MESSAGE_TYPES",
    "STAGE_SPEAKERS",
    "AdvocateRole",
    "AdvocateTurnOutput",
    "ArgumentDraft",
    "ElementRef",
    "MAX_ARGUMENTS_PER_TURN",
    "AdvocacyFlag",
    "AdvocateTurnValidator",
    "AdvocateValidationReport",
]
