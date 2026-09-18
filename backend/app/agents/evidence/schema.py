"""Structured output contracts for the Evidence Agent

Two tasks, two contracts:

- ``EvidenceAnalysisOutput`` - neutral analysis of the record before the
  debate: claims and their status, how each evidence item bears on the case,
  contradictions, witness reliability, and missing evidence.
- ``EvidenceReviewOutput`` - review of the arguments the parties have made:
  whether what each argument cites actually supports its claim.

Neither contract has any field for guilt, innocence, or a recommended
outcome. The Evidence Agent does not decide the case.
"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from ..advocate.schema import ElementRef


class ClaimStatus(str, Enum):
    """Spec section 6: established, disputed, or unsupported"""

    ESTABLISHED = "established"
    DISPUTED = "disputed"
    UNSUPPORTED = "unsupported"


class Directness(str, Enum):
    """How an evidence item bears on the facts (rules E001, E002)"""

    DIRECT = "direct"
    CIRCUMSTANTIAL = "circumstantial"


class ReliabilityRating(str, Enum):
    """Witness reliability band (rule E003)"""

    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class ArgumentSupport(str, Enum):
    """How well an argument's citations support its claim"""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"


# ============================================================================
# EVIDENCE_ANALYSIS
# ============================================================================


class ClaimAssessment(BaseModel):
    """One important claim and what the record says about it"""

    claim: str = Field(..., min_length=1, description="The claim, stated neutrally")
    fact_ids: List[str] = Field(..., description="Facts in the record the claim concerns")
    supporting_evidence_ids: List[str]
    supporting_witness_ids: List[str]
    contradicting_evidence_ids: List[str]
    contradicting_witness_ids: List[str]
    status: ClaimStatus
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., min_length=1)


class EvidenceAssessment(BaseModel):
    """How one evidence item bears on the case"""

    evidence_id: str
    directness: Directness
    fact_ids: List[str] = Field(..., description="Facts it bears on")
    reliability_concerns: List[str] = Field(
        ..., description="Grounds on which its reliability could be questioned (may be empty)"
    )
    reasoning: str = Field(..., min_length=1)


class Contradiction(BaseModel):
    """Two or more items in the record that cannot all be true (rule E004)"""

    description: str = Field(..., min_length=1)
    evidence_ids: List[str]
    witness_ids: List[str]
    fact_ids: List[str]
    significance: str = Field(..., min_length=1, description="Why it matters to the case")


class WitnessAssessment(BaseModel):
    """Reliability of one witness under rule E003"""

    witness_id: str
    rating: ReliabilityRating
    grounds: List[str] = Field(
        ..., description="E003 grounds: contradiction, memory, bias, opportunity, interest"
    )
    reasoning: str = Field(..., min_length=1)


class MissingEvidence(BaseModel):
    """Evidence the record lacks that bears on a legal element"""

    description: str = Field(..., min_length=1)
    elements: List[ElementRef] = Field(..., description="Legal elements it bears on")
    why_it_matters: str = Field(..., min_length=1)


class EvidenceAnalysisOutput(BaseModel):
    """Complete output of the EVIDENCE_ANALYSIS task"""

    claims: List[ClaimAssessment]
    evidence: List[EvidenceAssessment]
    contradictions: List[Contradiction]
    witnesses: List[WitnessAssessment]
    missing_evidence: List[MissingEvidence]
    summary: str = Field(..., min_length=1)


# ============================================================================
# EVIDENCE_REVIEW
# ============================================================================


class ArgumentReview(BaseModel):
    """Whether one argument's citations support its claim"""

    argument_id: str
    support: ArgumentSupport
    issues: List[str] = Field(
        ..., description="Specific problems: overclaiming, contradicted, miscited (may be empty)"
    )
    reasoning: str = Field(..., min_length=1)


class EvidenceReviewOutput(BaseModel):
    """Complete output of the EVIDENCE_REVIEW task"""

    reviews: List[ArgumentReview]
    summary: str = Field(..., min_length=1)
