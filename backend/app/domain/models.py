"""Core domain models for the Court Simulation System

These Pydantic models represent the core domain entities.
They are separate from database models and LLM interactions.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime"""
    return datetime.now(timezone.utc)


# ============================================================================
# Enumerations
# ============================================================================


class FactStatus(str, Enum):
    """Status of a fact in the case"""

    ESTABLISHED = "established"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


class EvidenceType(str, Enum):
    """Types of evidence"""

    PHYSICAL = "physical"
    TESTIMONIAL = "testimonial"
    DOCUMENTARY = "documentary"
    DIGITAL = "digital"
    FORENSIC = "forensic"
    CIRCUMSTANTIAL = "circumstantial"


class LegalCategory(str, Enum):
    """Categories of legal rules"""

    OFFENSE = "offense"
    DEFENSE = "defense"
    PRINCIPLE = "principle"
    EVIDENCE_RULE = "evidence_rule"
    PROCEDURE = "procedure"


class CaseStatus(str, Enum):
    """Status of a case"""

    INITIALIZED = "initialized"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class CaseType(str, Enum):
    """Type of legal case"""

    CRIMINAL = "criminal"
    CIVIL = "civil"


class CourtStage(str, Enum):
    """Stages of court procedure, in order (spec section 14)"""

    CASE_INITIALIZATION = "CASE_INITIALIZATION"
    EVIDENCE_ANALYSIS = "EVIDENCE_ANALYSIS"
    PROSECUTION_OPENING = "PROSECUTION_OPENING"
    DEFENSE_OPENING = "DEFENSE_OPENING"
    PROSECUTION_ARGUMENT = "PROSECUTION_ARGUMENT"
    DEFENSE_ARGUMENT = "DEFENSE_ARGUMENT"
    CROSS_EXAMINATION = "CROSS_EXAMINATION"
    EVIDENCE_REVIEW = "EVIDENCE_REVIEW"
    JUDGE_QUESTIONS = "JUDGE_QUESTIONS"
    PROSECUTION_REBUTTAL = "PROSECUTION_REBUTTAL"
    DEFENSE_REBUTTAL = "DEFENSE_REBUTTAL"
    CLOSING_ARGUMENTS = "CLOSING_ARGUMENTS"
    JURY_INDEPENDENT_DELIBERATION = "JURY_INDEPENDENT_DELIBERATION"
    JURY_DELIBERATION = "JURY_DELIBERATION"
    JUDGE_DECISION = "JUDGE_DECISION"
    LEGAL_PROCESS_AUDIT = "LEGAL_PROCESS_AUDIT"
    CASE_COMPLETE = "CASE_COMPLETE"


class MessageType(str, Enum):
    """Kinds of structured message exchanged in court"""

    OPENING_STATEMENT = "opening_statement"
    ARGUMENT = "argument"
    REBUTTAL = "rebuttal"
    CLOSING_STATEMENT = "closing_statement"
    DECISION = "decision"


# ============================================================================
# Core Domain Models
# ============================================================================


class Fact(BaseModel):
    """A fact in the case

    Facts are the foundational elements that may be established, disputed, or unknown.
    They should not be confused with evidence or arguments.
    """

    fact_id: str = Field(..., description="Unique identifier for the fact")
    description: str = Field(..., description="Clear statement of the fact")
    source: str = Field(..., description="Where this fact originated (e.g., 'case_file', 'E001')")
    status: FactStatus = Field(
        default=FactStatus.UNKNOWN, description="Whether fact is established, disputed, or unknown"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata about the fact"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "fact_id": "F001",
                "description": "Alex entered David's house at 11:45 PM",
                "source": "case_file",
                "status": "established",
                "metadata": {"timestamp": "2024-01-15T23:45:00"},
            }
        }
    )


class Evidence(BaseModel):
    """Evidence in the case

    Evidence is information that may support or contradict claims.
    Evidence cannot be modified by agents - it is authoritative.
    """

    evidence_id: str = Field(..., description="Unique identifier for the evidence")
    type: EvidenceType = Field(..., description="Type of evidence")
    description: str = Field(..., description="Description of the evidence")
    source: str = Field(..., description="Origin of the evidence")
    supports: List[str] = Field(
        default_factory=list, description="List of claim/fact IDs this evidence supports"
    )
    contradicts: List[str] = Field(
        default_factory=list, description="List of claim/fact IDs this evidence contradicts"
    )
    reliability: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Reliability score (0.0 to 1.0)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata about the evidence"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "evidence_id": "E001",
                "type": "physical",
                "description": "Broken window at entry point",
                "source": "crime_scene_investigation",
                "supports": ["F002"],
                "contradicts": [],
                "reliability": 0.95,
                "metadata": {"collected_by": "Officer Johnson", "date": "2024-01-16"},
            }
        }
    )


class Witness(BaseModel):
    """Witness in the case

    Witnesses provide testimony which serves as evidence.
    Reliability can be challenged based on various factors.
    """

    witness_id: str = Field(..., description="Unique identifier for the witness")
    name: str = Field(..., description="Name of the witness")
    statement: str = Field(..., description="Witness statement or testimony")
    reliability_factors: Dict[str, Any] = Field(
        default_factory=dict,
        description="Factors affecting reliability (bias, memory, opportunity to observe, etc.)",
    )
    related_evidence: List[str] = Field(
        default_factory=list, description="Evidence IDs related to this witness"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata about the witness"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "witness_id": "W001",
                "name": "David Thompson",
                "statement": "I heard glass breaking and confronted an intruder in my home.",
                "reliability_factors": {
                    "bias": "victim_in_case",
                    "opportunity_to_observe": "high",
                    "memory_quality": "good",
                },
                "related_evidence": ["E001", "E003"],
                "metadata": {"interviewed_date": "2024-01-16"},
            }
        }
    )


class Condition(BaseModel):
    """A condition that must be satisfied for a legal rule

    Conditions are part of structured legal rules.
    They represent elements that must be proven or established.
    """

    id: str = Field(..., description="Condition identifier")
    description: str = Field(..., description="Description of what must be satisfied")
    required: bool = Field(default=True, description="Whether this condition is required")
    depends_on_rule: Optional[str] = Field(
        default=None,
        description=(
            "Rule ID whose satisfaction determines this condition "
            "(e.g. LAW_102 'Assault' element depends on LAW_101)"
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "C1",
                "description": "Defendant reasonably believed they faced unlawful physical attack",
                "required": True,
            }
        }
    )


class LegalRule(BaseModel):
    """A legal rule in the jurisdiction

    Legal rules are structured and authoritative.
    They define offenses, defenses, principles, and evidence rules.
    """

    rule_id: str = Field(..., description="Unique identifier for the rule")
    name: str = Field(..., description="Name of the legal rule")
    category: LegalCategory = Field(..., description="Category of the rule")
    description: str = Field(..., description="Description of the rule")
    conditions: List[Condition] = Field(
        default_factory=list, description="Conditions that must be satisfied"
    )
    effect: str = Field(..., description="Effect or consequence when conditions are met")
    jurisdiction: str = Field(
        default="Republic of Arandia", description="Jurisdiction where rule applies"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata about the rule"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rule_id": "LAW_201",
                "name": "Self Defense",
                "category": "defense",
                "description": "A person may use reasonable force to defend against unlawful attack",
                "conditions": [
                    {
                        "id": "C1",
                        "description": "Reasonable belief of unlawful physical attack",
                        "required": True,
                    },
                    {"id": "C2", "description": "Force was necessary", "required": True},
                    {
                        "id": "C3",
                        "description": "Force was proportionate to threat",
                        "required": True,
                    },
                ],
                "effect": "self_defense_may_apply",
                "jurisdiction": "Republic of Arandia",
            }
        }
    )


class Argument(BaseModel):
    """An argument made by an agent

    Arguments must reference valid evidence and legal rules.
    They are the primary output of prosecution and defense agents.
    """

    argument_id: str = Field(..., description="Unique identifier for the argument")
    agent_id: str = Field(..., description="ID of agent making the argument")
    claim: str = Field(..., description="The claim being made")
    evidence_ids: List[str] = Field(
        default_factory=list, description="Evidence IDs supporting this argument"
    )
    fact_ids: List[str] = Field(
        default_factory=list, description="Fact IDs this argument relies on"
    )
    witness_ids: List[str] = Field(
        default_factory=list, description="Witness IDs whose testimony this argument relies on"
    )
    law_ids: List[str] = Field(
        default_factory=list, description="Legal rule IDs referenced in this argument"
    )
    counter_argument_ids: List[str] = Field(
        default_factory=list, description="Arguments this responds to or counters"
    )
    reasoning: str = Field(..., description="Reasoning supporting the claim")
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence in the argument (0.0 to 1.0)"
    )
    timestamp: datetime = Field(default_factory=utc_now, description="When argument was made")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "argument_id": "ARG001",
                "agent_id": "prosecution_agent",
                "claim": "The defendant committed burglary by entering the property without authorization",
                "evidence_ids": ["E001", "E003"],
                "law_ids": ["LAW_104"],
                "counter_argument_ids": [],
                "reasoning": "Evidence E001 shows forced entry, and E003 confirms no authorization was given.",
                "confidence": 0.85,
            }
        }
    )


class Verdict(BaseModel):
    """A verdict or decision

    Produced by judge or jury agents.
    Must clearly separate findings from decision.
    """

    verdict_id: str = Field(..., description="Unique identifier for the verdict")
    case_id: str = Field(..., description="Case this verdict relates to")
    agent_id: str = Field(..., description="Agent who produced this verdict (judge or jury member)")
    charges: List[str] = Field(..., description="Charges being decided")
    decision: str = Field(..., description="The verdict decision (guilty/not guilty/etc)")
    reasoning: str = Field(..., description="Detailed reasoning for the decision")
    evidence_used: List[str] = Field(
        default_factory=list, description="Evidence IDs relied upon"
    )
    laws_used: List[str] = Field(default_factory=list, description="Legal rule IDs applied")
    unresolved_questions: List[str] = Field(
        default_factory=list, description="Questions that remain unresolved"
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence in the verdict (0.0 to 1.0)"
    )
    timestamp: datetime = Field(default_factory=utc_now, description="When verdict was made")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "verdict_id": "V001",
                "case_id": "CASE_001",
                "agent_id": "judge_agent",
                "charges": ["aggravated_assault"],
                "decision": "not_guilty",
                "reasoning": "Self-defense elements were established with sufficient evidence.",
                "evidence_used": ["E001", "E003", "W001"],
                "laws_used": ["LAW_201", "LAW_102"],
                "unresolved_questions": ["Whether force was proportionate"],
                "confidence": 0.75,
            }
        }
    )


class AuditReport(BaseModel):
    """Audit report produced by Legal Process Auditor

    Inspects the simulation for violations and issues.
    Does not decide the case - only evaluates process quality.
    """

    audit_id: str = Field(..., description="Unique identifier for the audit")
    case_id: str = Field(..., description="Case being audited")
    evidence_violations: List[Dict[str, Any]] = Field(
        default_factory=list, description="Evidence-related violations detected"
    )
    legal_violations: List[Dict[str, Any]] = Field(
        default_factory=list, description="Legal rule violations detected"
    )
    procedural_violations: List[Dict[str, Any]] = Field(
        default_factory=list, description="Procedural violations detected"
    )
    reasoning_issues: List[Dict[str, Any]] = Field(
        default_factory=list, description="Issues with agent reasoning"
    )
    hallucinations: List[Dict[str, Any]] = Field(
        default_factory=list, description="Detected hallucinations (invented IDs/facts)"
    )
    final_assessment: str = Field(..., description="Overall assessment of simulation quality")
    timestamp: datetime = Field(default_factory=utc_now, description="When audit was performed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "audit_id": "AUD001",
                "case_id": "CASE_001",
                "evidence_violations": [],
                "legal_violations": [],
                "procedural_violations": [],
                "reasoning_issues": [
                    {"agent": "prosecution", "issue": "Circular reasoning in ARG003"}
                ],
                "hallucinations": [],
                "final_assessment": "Simulation completed with high integrity. Minor reasoning issue detected but did not affect outcome.",
            }
        }
    )


class Case(BaseModel):
    """A legal case in the system

    The top-level entity representing an entire case.
    Contains facts, evidence, witnesses, charges, and applicable laws.
    """

    case_id: str = Field(..., description="Unique identifier for the case")
    title: str = Field(..., description="Case title")
    description: str = Field(..., description="Case description/summary")
    jurisdiction: str = Field(
        default="Republic of Arandia", description="Jurisdiction handling the case"
    )
    case_type: CaseType = Field(..., description="Type of case (criminal or civil)")
    defendant: str = Field(..., description="Name of the defendant")
    prosecution: str = Field(
        default="The People of Arandia", description="Name of prosecuting party"
    )
    facts: List[Fact] = Field(default_factory=list, description="Facts of the case")
    evidence: List[Evidence] = Field(default_factory=list, description="Evidence in the case")
    witnesses: List[Witness] = Field(default_factory=list, description="Witnesses in the case")
    charges: List[str] = Field(default_factory=list, description="Charges filed")
    applicable_laws: List[str] = Field(
        default_factory=list, description="Legal rule IDs that may apply"
    )
    status: CaseStatus = Field(default=CaseStatus.INITIALIZED, description="Current case status")
    created_at: datetime = Field(default_factory=utc_now, description="Case creation time")
    updated_at: datetime = Field(default_factory=utc_now, description="Last update time")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "case_id": "CASE_001",
                "title": "The Night Intruder",
                "description": "Home invasion and alleged self-defense case",
                "jurisdiction": "Republic of Arandia",
                "case_type": "criminal",
                "defendant": "Alex Johnson",
                "prosecution": "The People of Arandia",
                "charges": ["aggravated_assault", "burglary"],
                "applicable_laws": ["LAW_101", "LAW_102", "LAW_104", "LAW_201"],
                "status": "initialized",
            }
        }
    )


# ============================================================================
# Rule Evaluation Inputs
# ============================================================================


class BindingStance(str, Enum):
    """Whether a binding supports or contradicts a legal condition"""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


class ElementBinding(BaseModel):
    """Links case facts and evidence to a single condition of a legal rule

    Bindings are the bridge between the case record and the legal rules.
    They say *which* facts and evidence bear on a legal element, but never
    whether the element is satisfied - that conclusion belongs to the rule
    engine, which weighs the referenced material deterministically.

    In later phases an agent may propose bindings, but the engine always
    validates the referenced IDs and computes the outcome itself.
    """

    binding_id: str = Field(..., description="Unique identifier for the binding")
    case_id: str = Field(..., description="Case this binding belongs to")
    rule_id: str = Field(..., description="Legal rule the condition belongs to")
    condition_id: str = Field(..., description="Condition within the rule")
    subject: str = Field(
        ..., description="Party whose conduct is being evaluated (e.g. 'Alex Johnson')"
    )
    stance: BindingStance = Field(
        ..., description="Whether the referenced material supports or contradicts the condition"
    )
    fact_ids: List[str] = Field(default_factory=list, description="Fact IDs referenced")
    evidence_ids: List[str] = Field(default_factory=list, description="Evidence IDs referenced")
    note: str = Field(default="", description="Short explanation of the link")
    source: str = Field(
        default="case_file", description="Who produced this binding (case_file, agent id, ...)"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "binding_id": "B001",
                "case_id": "CASE_001",
                "rule_id": "LAW_104",
                "condition_id": "C1",
                "subject": "Alex Johnson",
                "stance": "supports",
                "fact_ids": ["F001", "F002"],
                "evidence_ids": ["E001", "E002"],
                "note": "Entry through a broken window without permission",
                "source": "case_file",
            }
        }
    )


# ============================================================================
# Agent Communication
# ============================================================================


class CourtMessage(BaseModel):
    """A structured message between agents (spec section 18)

    Agents never exchange free-form chat. Each turn in court is one message
    with a sender, a recipient, a type, the stage it belongs to, and explicit
    references to the arguments, evidence, and laws it carries.
    """

    message_id: str = Field(..., description="Unique identifier for the message")
    case_id: str = Field(..., description="Case the message belongs to")
    sender: str = Field(..., description="Agent that sent the message")
    recipient: str = Field(..., description="Agent the message is addressed to")
    message_type: MessageType = Field(..., description="Kind of message")
    stage: CourtStage = Field(..., description="Court stage in which it was sent")
    claim: str = Field(..., description="The message's central statement")
    argument_ids: List[str] = Field(
        default_factory=list, description="Arguments carried by this message"
    )
    evidence_ids: List[str] = Field(default_factory=list, description="Evidence cited")
    law_ids: List[str] = Field(default_factory=list, description="Legal rules cited")
    reasoning: str = Field(default="", description="Concise rationale")
    timestamp: datetime = Field(default_factory=utc_now, description="When it was sent")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message_id": "MSG-PR-OPEN",
                "case_id": "CASE_001",
                "sender": "prosecution_agent",
                "recipient": "judge_agent",
                "message_type": "opening_statement",
                "stage": "PROSECUTION_OPENING",
                "claim": "The evidence proves unlawful entry into the home.",
                "argument_ids": ["PR-OPEN-1"],
                "evidence_ids": ["E001", "E002"],
                "law_ids": ["LAW_104"],
                "reasoning": "E001 and E002 place Alex at the broken window.",
            }
        }
    )
