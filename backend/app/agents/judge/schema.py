"""Structured output contract for the Judge Agent

The judge must keep six things separate: established facts, disputed facts,
applicable rules, arguments considered, analysis, and the decision. Every
factual or legal statement carries the IDs it rests on, so the validation
layer can check each one against the case record.
"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class ElementAssessment(str, Enum):
    """How the judge assesses one required element of an offense"""

    ESTABLISHED = "established"
    NOT_ESTABLISHED = "not_established"
    DOUBTFUL = "doubtful"


class ChargeOutcome(str, Enum):
    """Decision on a single charge"""

    GUILTY = "guilty"
    NOT_GUILTY = "not_guilty"


class FactFinding(BaseModel):
    """A fact the judge treats as established"""

    fact_id: str = Field(..., description="ID of a fact in the case record")
    finding: str = Field(..., description="What the court finds, in one or two sentences")
    evidence_ids: List[str] = Field(..., description="Evidence the finding rests on")


class DisputedFinding(BaseModel):
    """A fact the parties or the evidence contest"""

    fact_id: str = Field(..., description="ID of a fact in the case record")
    issue: str = Field(..., description="What is in dispute")
    supporting_evidence_ids: List[str] = Field(..., description="Evidence supporting the fact")
    contradicting_evidence_ids: List[str] = Field(
        ..., description="Evidence contradicting the fact"
    )
    resolution: str = Field(..., description="How the court treats the dispute, and why")


class RuleApplication(BaseModel):
    """A legal rule the judge applies"""

    rule_id: str = Field(..., description="ID of a legal rule in the record")
    relevance: str = Field(..., description="Why the rule matters to this case")


class ElementFinding(BaseModel):
    """The judge's assessment of one condition of a charged offense"""

    condition_id: str = Field(..., description="Condition ID within the charged rule")
    assessment: ElementAssessment
    fact_ids: List[str] = Field(..., description="Facts relied on")
    evidence_ids: List[str] = Field(..., description="Evidence relied on")
    reasoning: str = Field(..., description="Concise rationale for the assessment")


class ChargeDecision(BaseModel):
    """The decision on one charge"""

    charge: str = Field(..., description="Charge exactly as listed in the case")
    rule_id: str = Field(..., description="Offense rule the charge is decided under")
    elements: List[ElementFinding] = Field(..., description="One entry per required condition")
    defenses_considered: List[str] = Field(
        ..., description="IDs of defense rules considered for this charge"
    )
    decision: ChargeOutcome
    reasoning: str = Field(..., description="Concise rationale connecting elements to decision")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence from 0.0 to 1.0")


class JudgeDecisionOutput(BaseModel):
    """Complete structured output of the Judge Agent"""

    established_facts: List[FactFinding]
    disputed_facts: List[DisputedFinding]
    applicable_rules: List[RuleApplication]
    arguments_considered: List[str] = Field(
        ..., description="IDs of party arguments considered (empty if none were presented)"
    )
    analysis: str = Field(..., description="Analysis linking facts, evidence, and law")
    charge_decisions: List[ChargeDecision]
    unresolved_questions: List[str]
    overall_confidence: float = Field(..., ge=0.0, le=1.0)

    def referenced_fact_ids(self) -> List[str]:
        """Every fact ID cited anywhere in the output, in first-seen order"""
        ids: List[str] = [f.fact_id for f in self.established_facts]
        ids += [f.fact_id for f in self.disputed_facts]
        for charge in self.charge_decisions:
            for element in charge.elements:
                ids += element.fact_ids
        return _unique(ids)

    def referenced_evidence_ids(self) -> List[str]:
        """Every evidence ID cited anywhere in the output, in first-seen order"""
        ids: List[str] = []
        for fact in self.established_facts:
            ids += fact.evidence_ids
        for disputed in self.disputed_facts:
            ids += disputed.supporting_evidence_ids + disputed.contradicting_evidence_ids
        for charge in self.charge_decisions:
            for element in charge.elements:
                ids += element.evidence_ids
        return _unique(ids)

    def referenced_rule_ids(self) -> List[str]:
        """Every legal rule ID cited anywhere in the output, in first-seen order"""
        ids: List[str] = [r.rule_id for r in self.applicable_rules]
        for charge in self.charge_decisions:
            ids.append(charge.rule_id)
            ids += charge.defenses_considered
        return _unique(ids)


def _unique(ids: List[str]) -> List[str]:
    seen: List[str] = []
    for item in ids:
        if item not in seen:
            seen.append(item)
    return seen
