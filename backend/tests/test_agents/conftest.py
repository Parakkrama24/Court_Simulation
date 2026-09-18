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
