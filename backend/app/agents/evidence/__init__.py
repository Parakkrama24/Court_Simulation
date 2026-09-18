"""Evidence Agent: neutral evidence analysis and argument review"""

from .agent import (
    EVIDENCE_AGENT_ID,
    EvidenceAgent,
    EvidenceAgentError,
    EvidenceAnalysis,
    EvidenceReview,
    evidence_context,
)
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT
from .provenance import ProvenanceRecord, trace_case_provenance, trace_provenance
from .schema import (
    ArgumentReview,
    ArgumentSupport,
    ClaimAssessment,
    ClaimStatus,
    Contradiction,
    Directness,
    EvidenceAnalysisOutput,
    EvidenceAssessment,
    EvidenceReviewOutput,
    MissingEvidence,
    ReliabilityRating,
    WitnessAssessment,
)
from .validation import (
    MAX_CLAIMS,
    EvidenceAnalysisValidator,
    EvidenceFlag,
    EvidenceReviewValidator,
    EvidenceValidationReport,
    reliability_band,
)

__all__ = [
    "EVIDENCE_AGENT_ID",
    "EvidenceAgent",
    "EvidenceAgentError",
    "EvidenceAnalysis",
    "EvidenceReview",
    "evidence_context",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "ProvenanceRecord",
    "trace_case_provenance",
    "trace_provenance",
    "ArgumentReview",
    "ArgumentSupport",
    "ClaimAssessment",
    "ClaimStatus",
    "Contradiction",
    "Directness",
    "EvidenceAnalysisOutput",
    "EvidenceAssessment",
    "EvidenceReviewOutput",
    "MissingEvidence",
    "ReliabilityRating",
    "WitnessAssessment",
    "MAX_CLAIMS",
    "EvidenceAnalysisValidator",
    "EvidenceFlag",
    "EvidenceReviewValidator",
    "EvidenceValidationReport",
    "reliability_band",
]
