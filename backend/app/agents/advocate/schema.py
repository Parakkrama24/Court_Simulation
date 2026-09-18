"""Structured output contract for the Prosecution and Defense agents

One turn in court is a statement plus a list of arguments. Every argument
names the charges and legal elements it addresses, cites the facts, evidence,
and witnesses it rests on, lists any assumptions separately from facts, and
names the opposing arguments it answers.

The model never assigns argument IDs. The court assigns them after the turn
passes validation, so every ID in the debate is real.
"""

from typing import List

from pydantic import BaseModel, Field


class ElementRef(BaseModel):
    """A legal element: one condition of one rule"""

    rule_id: str = Field(..., description="Legal rule ID")
    condition_id: str = Field(..., description="Condition ID within that rule")


class ArgumentDraft(BaseModel):
    """One argument as the advocate writes it"""

    charges: List[str] = Field(..., description="Charges this argument concerns")
    elements: List[ElementRef] = Field(
        ..., description="Legal elements this argument addresses (may be empty)"
    )
    claim: str = Field(..., min_length=1, description="The claim, in one or two sentences")
    fact_ids: List[str] = Field(..., description="Facts relied on")
    evidence_ids: List[str] = Field(..., description="Evidence relied on")
    witness_ids: List[str] = Field(..., description="Witnesses whose testimony is relied on")
    law_ids: List[str] = Field(..., description="Legal rules invoked")
    responds_to: List[str] = Field(
        ..., description="IDs of opposing arguments this one answers (empty if none)"
    )
    assumptions: List[str] = Field(
        ..., description="Anything the argument assumes that the record does not establish"
    )
    reasoning: str = Field(..., min_length=1, description="Concise rationale")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence from 0.0 to 1.0")


class AdvocateTurnOutput(BaseModel):
    """Complete output of one advocate turn"""

    statement: str = Field(
        ..., min_length=1, description="The statement to the court for this stage"
    )
    arguments: List[ArgumentDraft]
