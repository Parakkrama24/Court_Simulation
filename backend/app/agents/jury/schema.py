"""Structured output contracts for jury agents

Spec section 8: each juror outputs a verdict, reasoning, the evidence and
legal rules relied upon, uncertainties, and confidence. Verdicts are given
per charge. The deliberation round uses the same contract plus the juror's
response to the rest of the panel.
"""

from typing import List

from pydantic import BaseModel, Field

from ..judge.schema import ChargeOutcome


class JurorChargeVerdict(BaseModel):
    """One juror's verdict on one charge"""

    charge: str = Field(..., description="Charge exactly as listed in the case")
    verdict: ChargeOutcome
    fact_ids: List[str] = Field(..., description="Facts relied upon")
    evidence_ids: List[str] = Field(..., description="Evidence relied upon")
    witness_ids: List[str] = Field(..., description="Witnesses whose testimony was relied upon")
    rule_ids: List[str] = Field(
        ..., description="Legal rules relied upon, including the offense charged"
    )
    reasoning: str = Field(..., min_length=1, description="Concise rationale")
    confidence: float = Field(..., ge=0.0, le=1.0)


class JurorVerdictOutput(BaseModel):
    """A juror's complete independent decision"""

    charge_verdicts: List[JurorChargeVerdict]
    arguments_considered: List[str] = Field(
        ..., description="IDs of party arguments weighed (empty if none were presented)"
    )
    uncertainties: List[str] = Field(..., description="What the juror remains unsure about")
    reasoning: str = Field(..., min_length=1, description="Overall rationale")
    confidence: float = Field(..., ge=0.0, le=1.0)


class JurorDeliberationOutput(JurorVerdictOutput):
    """A juror's decision after seeing the rest of the panel"""

    response_to_panel: str = Field(
        ...,
        min_length=1,
        description="What the juror made of the other jurors' views, and why",
    )
