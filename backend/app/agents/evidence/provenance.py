"""Evidence provenance, computed from the record

Where a piece of evidence came from is a fact about the record, not an
interpretation, so it is derived here deterministically rather than asked of
a model: the source, who collected or examined it and when, the witness it
comes from (if any), and which facts it bears on.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.domain import Case, Evidence

# Metadata keys that name the person who produced the evidence, in the order
# they are preferred when several are present.
_HANDLER_KEYS = ("collected_by", "examined_by", "searched_by", "interviewed_by", "recorded_by")
_DATE_KEYS = ("date", "call_time", "interviewed_date")


class ProvenanceRecord(BaseModel):
    """The chain of custody the record gives for one evidence item"""

    evidence_id: str
    evidence_type: str
    source: str = Field(..., description="Origin of the evidence as recorded")
    handled_by: Optional[str] = Field(
        default=None, description="Who collected, examined, or recorded it"
    )
    date: Optional[str] = Field(default=None, description="When, if recorded")
    witness_id: Optional[str] = Field(
        default=None, description="Witness the evidence comes from, if testimonial"
    )
    supports_facts: List[str] = Field(default_factory=list)
    contradicts_facts: List[str] = Field(default_factory=list)
    recorded_reliability: float
    gaps: List[str] = Field(
        default_factory=list, description="Provenance details the record does not give"
    )


def _first(metadata: Dict[str, object], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = metadata.get(key)
        if value:
            return str(value)
    return None


def trace_provenance(evidence: Evidence, case: Case) -> ProvenanceRecord:
    """Provenance of one evidence item"""
    witness_ids = {w.witness_id for w in case.witnesses}
    witness_id = None
    for candidate in (evidence.metadata.get("witness"), evidence.source):
        if isinstance(candidate, str) and candidate in witness_ids:
            witness_id = candidate
            break

    handled_by = _first(evidence.metadata, _HANDLER_KEYS)
    date = _first(evidence.metadata, _DATE_KEYS)

    gaps: List[str] = []
    if handled_by is None and witness_id is None:
        gaps.append("no record of who collected or produced it")
    if date is None:
        gaps.append("no collection date recorded")
    if not evidence.supports and not evidence.contradicts:
        gaps.append("not linked to any fact in the record")

    return ProvenanceRecord(
        evidence_id=evidence.evidence_id,
        evidence_type=evidence.type.value,
        source=evidence.source,
        handled_by=handled_by,
        date=date,
        witness_id=witness_id,
        supports_facts=list(evidence.supports),
        contradicts_facts=list(evidence.contradicts),
        recorded_reliability=evidence.reliability,
        gaps=gaps,
    )


def trace_case_provenance(case: Case) -> List[ProvenanceRecord]:
    """Provenance of every evidence item, in record order"""
    return [trace_provenance(item, case) for item in case.evidence]
