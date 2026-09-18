"""Advocate roles and the court stages they speak in"""

from enum import Enum
from typing import Dict, List

from app.domain import CourtStage, MessageType


class AdvocateRole(str, Enum):
    """The two adversarial parties"""

    PROSECUTION = "prosecution"
    DEFENSE = "defense"

    @property
    def agent_id(self) -> str:
        return f"{self.value}_agent"

    @property
    def code(self) -> str:
        """Short prefix used in argument IDs"""
        return "PR" if self is AdvocateRole.PROSECUTION else "DF"

    @property
    def opponent(self) -> "AdvocateRole":
        if self is AdvocateRole.PROSECUTION:
            return AdvocateRole.DEFENSE
        return AdvocateRole.PROSECUTION


# Which party speaks at each adversarial stage, in speaking order.
STAGE_SPEAKERS: Dict[CourtStage, List[AdvocateRole]] = {
    CourtStage.PROSECUTION_OPENING: [AdvocateRole.PROSECUTION],
    CourtStage.DEFENSE_OPENING: [AdvocateRole.DEFENSE],
    CourtStage.PROSECUTION_ARGUMENT: [AdvocateRole.PROSECUTION],
    CourtStage.DEFENSE_ARGUMENT: [AdvocateRole.DEFENSE],
    CourtStage.PROSECUTION_REBUTTAL: [AdvocateRole.PROSECUTION],
    CourtStage.DEFENSE_REBUTTAL: [AdvocateRole.DEFENSE],
    CourtStage.CLOSING_ARGUMENTS: [AdvocateRole.PROSECUTION, AdvocateRole.DEFENSE],
}

STAGE_MESSAGE_TYPES: Dict[CourtStage, MessageType] = {
    CourtStage.PROSECUTION_OPENING: MessageType.OPENING_STATEMENT,
    CourtStage.DEFENSE_OPENING: MessageType.OPENING_STATEMENT,
    CourtStage.PROSECUTION_ARGUMENT: MessageType.ARGUMENT,
    CourtStage.DEFENSE_ARGUMENT: MessageType.ARGUMENT,
    CourtStage.PROSECUTION_REBUTTAL: MessageType.REBUTTAL,
    CourtStage.DEFENSE_REBUTTAL: MessageType.REBUTTAL,
    CourtStage.CLOSING_ARGUMENTS: MessageType.CLOSING_STATEMENT,
}

STAGE_CODES: Dict[CourtStage, str] = {
    CourtStage.PROSECUTION_OPENING: "OPEN",
    CourtStage.DEFENSE_OPENING: "OPEN",
    CourtStage.PROSECUTION_ARGUMENT: "ARG",
    CourtStage.DEFENSE_ARGUMENT: "ARG",
    CourtStage.PROSECUTION_REBUTTAL: "REB",
    CourtStage.DEFENSE_REBUTTAL: "REB",
    CourtStage.CLOSING_ARGUMENTS: "CLOSE",
}

REBUTTAL_STAGES = {CourtStage.PROSECUTION_REBUTTAL, CourtStage.DEFENSE_REBUTTAL}
