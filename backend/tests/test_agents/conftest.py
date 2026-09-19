"""Fixtures for Judge Agent tests

``valid_decision`` is a hand-written decision for CASE_001 that cites only
real IDs, decides both charges, assesses every required element, and agrees
with the rule engine. Tests mutate copies of it to stage specific failures.
"""

import copy
from typing import Any, Callable, Dict

import pytest

from app.rules import CaseEvaluation, RuleEngine
from app.seed import get_case_001_bindings, get_case_by_id

VALID_DECISION: Dict[str, Any] = {
    "established_facts": [
        {
            "fact_id": "F001",
            "finding": "Alex entered David's house at 11:45 PM without permission.",
            "evidence_ids": ["E001", "E002"],
        },
        {
            "fact_id": "F005",
            "finding": "David struck Alex with a metal baseball bat.",
            "evidence_ids": ["E003"],
        },
    ],
    "disputed_facts": [
        {
            "fact_id": "F004",
            "issue": "Whether Alex physically attacked David.",
            "supporting_evidence_ids": ["E006"],
            "contradicting_evidence_ids": ["E007"],
            "resolution": "Not established: no defensive wounds and only indirect testimony.",
        }
    ],
    "applicable_rules": [
        {"rule_id": "LAW_104", "relevance": "Burglary charge."},
        {"rule_id": "LAW_101", "relevance": "Assault charge."},
        {"rule_id": "P004", "relevance": "Doubt on an element requires acquittal."},
    ],
    "arguments_considered": [],
    "analysis": "Entry is proven; intent is not. The alleged attack rests on disputed F004.",
    "charge_decisions": [
        {
            "charge": "burglary",
            "rule_id": "LAW_104",
            "elements": [
                {
                    "condition_id": "C1",
                    "assessment": "established",
                    "fact_ids": ["F001", "F002"],
                    "evidence_ids": ["E001", "E002"],
                    "reasoning": "Broken window and footprints show unauthorized entry.",
                },
                {
                    "condition_id": "C2",
                    "assessment": "not_established",
                    "fact_ids": [],
                    "evidence_ids": [],
                    "reasoning": "Nothing in the record speaks to intent to commit an offense.",
                },
            ],
            "defenses_considered": [],
            "decision": "not_guilty",
            "reasoning": "The intent element of LAW_104 is not proven.",
            "confidence": 0.85,
        },
        {
            "charge": "assault",
            "rule_id": "LAW_101",
            "elements": [
                {
                    "condition_id": "C1",
                    "assessment": "doubtful",
                    "fact_ids": ["F004"],
                    "evidence_ids": ["E006", "E007"],
                    "reasoning": "Only David's disputed account supports it; E007 contradicts it.",
                },
                {
                    "condition_id": "C2",
                    "assessment": "doubtful",
                    "fact_ids": ["F004"],
                    "evidence_ids": ["E007"],
                    "reasoning": "No physical evidence of contact by Alex.",
                },
                {
                    "condition_id": "C3",
                    "assessment": "established",
                    "fact_ids": ["F001"],
                    "evidence_ids": ["E001"],
                    "reasoning": "Any force by an unlawful intruder would be unlawful.",
                },
            ],
            "defenses_considered": [],
            "decision": "not_guilty",
            "reasoning": "Force and contact are not proven beyond reasonable doubt.",
            "confidence": 0.75,
        },
    ],
    "unresolved_questions": ["What did Alex intend when he entered the house?"],
    "overall_confidence": 0.8,
}


@pytest.fixture
def case():
    return get_case_by_id("CASE_001")


@pytest.fixture
def evaluation(case) -> CaseEvaluation:
    return RuleEngine().evaluate_case(case, get_case_001_bindings())


@pytest.fixture
def valid_decision() -> Dict[str, Any]:
    return copy.deepcopy(VALID_DECISION)


@pytest.fixture
def decision_with() -> Callable[..., Dict[str, Any]]:
    """Build a modified copy of the valid decision"""

    def build(mutate: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
        decision = copy.deepcopy(VALID_DECISION)
        mutate(decision)
        return decision

    return build


# ============================================================================
# Advocate turns
# ============================================================================


def prosecution_turn(responds_to=None) -> Dict[str, Any]:
    """A well-formed prosecution turn for CASE_001"""
    responds_to = list(responds_to or [])
    return {
        "statement": "The evidence proves Alex broke into the home and attacked David.",
        "arguments": [
            {
                "charges": ["burglary"],
                "elements": [{"rule_id": "LAW_104", "condition_id": "C1"}],
                "claim": "Alex entered David's home without permission through a broken window.",
                "fact_ids": ["F001", "F002"],
                "evidence_ids": ["E001", "E002"],
                "witness_ids": [],
                "law_ids": ["LAW_104"],
                "responds_to": responds_to,
                "assumptions": [],
                "reasoning": "Glass inside the kitchen and Alex's footprints at the window.",
                "confidence": 0.9,
            },
            {
                "charges": ["assault"],
                "elements": [
                    {"rule_id": "LAW_101", "condition_id": "C1"},
                    {"rule_id": "LAW_101", "condition_id": "C2"},
                ],
                "claim": "Alex came at David aggressively inside the house.",
                "fact_ids": ["F004"],
                "evidence_ids": ["E006"],
                "witness_ids": ["W001"],
                "law_ids": [],
                "responds_to": responds_to,
                "assumptions": ["David's account of the confrontation is accurate."],
                "reasoning": "David's statement and the neighbour hearing a struggle.",
                "confidence": 0.6,
            },
        ],
    }


def defense_turn(responds_to=None) -> Dict[str, Any]:
    """A well-formed defense turn for CASE_001"""
    responds_to = list(responds_to or [])
    return {
        "statement": "Nothing proves Alex intended a crime, and nothing proves he attacked.",
        "arguments": [
            {
                "charges": ["burglary"],
                "elements": [{"rule_id": "LAW_104", "condition_id": "C2"}],
                "claim": "No evidence shows Alex intended to commit an offense inside.",
                "fact_ids": ["F001"],
                "evidence_ids": [],
                "witness_ids": ["W003"],
                "law_ids": ["LAW_104", "P002"],
                "responds_to": responds_to,
                "assumptions": ["Alex's account of confusing the address may be true."],
                "reasoning": "The record is silent on intent; the burden is the prosecution's.",
                "confidence": 0.8,
            },
            {
                "charges": ["assault"],
                "elements": [{"rule_id": "LAW_101", "condition_id": "C1"}],
                "claim": "The absence of defensive wounds contradicts any attack by Alex.",
                "fact_ids": [],
                "evidence_ids": ["E007"],
                "witness_ids": [],
                "law_ids": ["P004"],
                "responds_to": responds_to,
                "assumptions": [],
                "reasoning": "E007 is forensic and reliable; F004 is disputed.",
                "confidence": 0.75,
            },
        ],
    }


@pytest.fixture
def pro_turn() -> Callable[..., Dict[str, Any]]:
    return prosecution_turn


@pytest.fixture
def def_turn() -> Callable[..., Dict[str, Any]]:
    return defense_turn


# ============================================================================
# Evidence Agent
# ============================================================================

VALID_ANALYSIS: Dict[str, Any] = {
    "claims": [
        {
            "claim": "Alex entered the house without permission through a broken window.",
            "fact_ids": ["F001", "F002"],
            "supporting_evidence_ids": ["E001", "E002"],
            "supporting_witness_ids": [],
            "contradicting_evidence_ids": [],
            "contradicting_witness_ids": [],
            "status": "established",
            "confidence": 0.95,
            "reasoning": "Glass inside the kitchen and matching footprints; Alex concedes entry.",
        },
        {
            "claim": "Alex physically attacked David.",
            "fact_ids": ["F004"],
            "supporting_evidence_ids": ["E006"],
            "supporting_witness_ids": ["W001"],
            "contradicting_evidence_ids": ["E007"],
            "contradicting_witness_ids": ["W003"],
            "status": "disputed",
            "confidence": 0.6,
            "reasoning": "David's account against the absence of defensive wounds; the forensic "
            "evidence is the stronger side.",
        },
        {
            "claim": "Alex intended to commit an offense inside the house.",
            "fact_ids": [],
            "supporting_evidence_ids": [],
            "supporting_witness_ids": [],
            "contradicting_evidence_ids": [],
            "contradicting_witness_ids": [],
            "status": "unsupported",
            "confidence": 0.9,
            "reasoning": "Nothing in the record speaks to intent.",
        },
        {
            "claim": "David struck Alex with a metal bat, causing serious injuries.",
            "fact_ids": ["F005", "F006"],
            "supporting_evidence_ids": ["E003", "E004"],
            "supporting_witness_ids": [],
            "contradicting_evidence_ids": [],
            "contradicting_witness_ids": [],
            "status": "established",
            "confidence": 0.97,
            "reasoning": "Blood on the bat and the medical report.",
        },
    ],
    "evidence": [
        {
            "evidence_id": evidence_id,
            "directness": directness,
            "fact_ids": fact_ids,
            "reliability_concerns": concerns,
            "reasoning": "Assessed from its source and content.",
        }
        for evidence_id, directness, fact_ids, concerns in [
            ("E001", "direct", ["F001", "F002"], []),
            ("E002", "circumstantial", ["F001"], []),
            ("E003", "direct", ["F005"], []),
            ("E004", "direct", ["F006"], []),
            ("E005", "direct", ["F007"], ["no record of who retrieved the recording"]),
            ("E006", "circumstantial", ["F003"], ["heard, not seen"]),
            ("E007", "circumstantial", ["F004"], []),
            ("E008", "direct", ["F008"], []),
        ]
    ],
    "contradictions": [
        {
            "description": "David says Alex came at him; Alex denies it and David had no "
            "defensive wounds.",
            "evidence_ids": ["E007"],
            "witness_ids": ["W001", "W003"],
            "fact_ids": ["F004"],
            "significance": "Decides whether any force by Alex is proven.",
        }
    ],
    "witnesses": [
        {
            "witness_id": "W001",
            "rating": "moderate",
            "grounds": ["bias", "personal interest"],
            "reasoning": "Good opportunity to observe; strong interest in the outcome.",
        },
        {
            "witness_id": "W002",
            "rating": "high",
            "grounds": [],
            "reasoning": "Independent neighbour, though she only heard the events.",
        },
        {
            "witness_id": "W003",
            "rating": "low",
            "grounds": ["bias", "memory", "contradiction", "personal interest"],
            "reasoning": "Defendant; possible trauma; conflicts with other evidence.",
        },
    ],
    "missing_evidence": [
        {
            "description": "Any evidence of what Alex intended to do inside.",
            "elements": [{"rule_id": "LAW_104", "condition_id": "C2"}],
            "why_it_matters": "Burglary requires intent to commit an offense inside.",
        }
    ],
    "summary": "Entry and David's use of force are established; whether Alex attacked is "
    "disputed; nothing speaks to Alex's intent.",
}


@pytest.fixture
def valid_analysis() -> Dict[str, Any]:
    return copy.deepcopy(VALID_ANALYSIS)


def review_for(argument_ids, support="supported", issues=None) -> Dict[str, Any]:
    """An evidence review covering ``argument_ids``"""
    return {
        "reviews": [
            {
                "argument_id": argument_id,
                "support": support,
                "issues": list(issues or []),
                "reasoning": "Checked against the cited record.",
            }
            for argument_id in argument_ids
        ],
        "summary": "Arguments reviewed against their citations.",
    }


# ============================================================================
# Jury
# ============================================================================


def juror_verdict(
    burglary: str = "not_guilty",
    assault: str = "not_guilty",
    considered=None,
    deliberation: bool = False,
) -> Dict[str, Any]:
    """A well-formed juror verdict for CASE_001"""
    output: Dict[str, Any] = {
        "charge_verdicts": [
            {
                "charge": "burglary",
                "verdict": burglary,
                "fact_ids": ["F001"],
                "evidence_ids": ["E001", "E002"],
                "witness_ids": [],
                "rule_ids": ["LAW_104", "P002"],
                "reasoning": "Entry is proven; intent is not.",
                "confidence": 0.8,
            },
            {
                "charge": "assault",
                "verdict": assault,
                "fact_ids": ["F004"],
                "evidence_ids": ["E007"],
                "witness_ids": ["W001"],
                "rule_ids": ["LAW_101", "P004"],
                "reasoning": "David's account is contradicted by the absence of defensive wounds.",
                "confidence": 0.7,
            },
        ],
        "arguments_considered": list(considered or []),
        "uncertainties": ["What Alex intended when he entered."],
        "reasoning": "The prosecution has not proven every element of either charge.",
        "confidence": 0.75,
    }
    if deliberation:
        output["response_to_panel"] = "I weighed the other jurors' points against the record."
    return output


@pytest.fixture
def juror() -> Callable[..., Dict[str, Any]]:
    return juror_verdict


# ============================================================================
# Legal Process Auditor
# ============================================================================


def auditor_output(findings=None) -> Dict[str, Any]:
    """A well-formed auditor-agent output for a quick CASE_001 trial"""
    return {
        "findings": list(
            findings
            if findings is not None
            else [
                {
                    "category": "reasoning",
                    "severity": "minor",
                    "issue_type": "self_contradiction",
                    "agent_id": "prosecution_agent",
                    "stage": "CLOSING_ARGUMENTS",
                    "description": "The closing restates PR-OPEN-2 without the assumption the "
                    "opening listed.",
                    "references": ["PR-OPEN-2", "PR-CLOSE-2", "F004"],
                }
            ]
        ),
        "decision_chain": [
            {"link": link, "rating": "sound", "note": "Cited and consistent."}
            for link in (
                "facts_to_evidence",
                "evidence_to_law",
                "law_to_analysis",
                "analysis_to_decision",
            )
        ],
        "final_assessment": "The trial followed procedure; one minor reasoning issue.",
    }
