"""Structured output contract for the Legal Process Auditor agent

The auditor reviews what deterministic checks cannot: self-contradiction,
misapplied law, assumptions treated as facts, and whether the final decision
connects FACTS -> EVIDENCE -> LAW -> ANALYSIS -> DECISION (spec section 23).
It reports on the process; it does not decide the case.
"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from .findings import AuditCategory, Severity


class ChainLink(str, Enum):
    """The four links of the decision chain"""

    FACTS_TO_EVIDENCE = "facts_to_evidence"
    EVIDENCE_TO_LAW = "evidence_to_law"
    LAW_TO_ANALYSIS = "law_to_analysis"
    ANALYSIS_TO_DECISION = "analysis_to_decision"


class LinkRating(str, Enum):
    SOUND = "sound"
    WEAK = "weak"
    BROKEN = "broken"


class AuditorFinding(BaseModel):
    """One issue the auditor found"""

    category: AuditCategory
    severity: Severity
    issue_type: str = Field(
        ..., min_length=1, description="Short snake_case label, e.g. self_contradiction"
    )
    agent_id: str = Field(..., description="Agent responsible, or empty if none")
    stage: str = Field(..., description="Court stage where it occurred, or empty")
    description: str = Field(..., min_length=1)
    references: List[str] = Field(
        ..., description="Argument, message, fact, evidence, witness, or rule IDs involved"
    )


class ChainAssessment(BaseModel):
    """One link of the judge's decision chain"""

    link: ChainLink
    rating: LinkRating
    note: str = Field(..., min_length=1)


class AuditorOutput(BaseModel):
    """Complete output of the Legal Process Auditor"""

    findings: List[AuditorFinding]
    decision_chain: List[ChainAssessment]
    final_assessment: str = Field(..., min_length=1)
