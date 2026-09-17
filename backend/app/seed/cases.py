"""Case seed data

Contains seed data for all initial test cases.
"""

from datetime import datetime
from typing import List
from app.domain import (
    Case,
    CaseType,
    CaseStatus,
    Fact,
    FactStatus,
    Evidence,
    EvidenceType,
    Witness,
)


def get_case_001() -> Case:
    """CASE_001 - The Night Intruder

    A home invasion and alleged self-defense case involving burglary,
    assault, and questions about proportionality of defensive force.
    """

    # Facts
    facts = [
        Fact(
            fact_id="F001",
            description="Alex entered David's house at 11:45 PM without permission",
            source="police_report",
            status=FactStatus.ESTABLISHED,
            metadata={"timestamp": "2024-01-15T23:45:00"},
        ),
        Fact(
            fact_id="F002",
            description="Entry was made through a broken window",
            source="E001",
            status=FactStatus.ESTABLISHED,
            metadata={"entry_point": "kitchen_window"},
        ),
        Fact(
            fact_id="F003",
            description="David confronted Alex inside the house",
            source="W001",
            status=FactStatus.ESTABLISHED,
        ),
        Fact(
            fact_id="F004",
            description="Alex physically attacked David",
            source="W001",
            status=FactStatus.DISPUTED,
            metadata={"disputed_by": "defense"},
        ),
        Fact(
            fact_id="F005",
            description="David struck Alex with a metal object",
            source="E003",
            status=FactStatus.ESTABLISHED,
        ),
        Fact(
            fact_id="F006",
            description="Alex suffered serious injuries including broken ribs and head trauma",
            source="E004",
            status=FactStatus.ESTABLISHED,
        ),
        Fact(
            fact_id="F007",
            description="David called emergency services after the incident",
            source="E005",
            status=FactStatus.ESTABLISHED,
        ),
        Fact(
            fact_id="F008",
            description="Alex had no weapon",
            source="police_report",
            status=FactStatus.ESTABLISHED,
        ),
    ]

    # Evidence
    evidence = [
        Evidence(
            evidence_id="E001",
            type=EvidenceType.PHYSICAL,
            description="Broken kitchen window with glass fragments on the floor inside",
            source="crime_scene_investigation",
            supports=["F001", "F002"],
            contradicts=[],
            reliability=0.95,
            metadata={
                "collected_by": "Officer Martinez",
                "date": "2024-01-16",
                "location": "kitchen_window",
            },
        ),
        Evidence(
            evidence_id="E002",
            type=EvidenceType.PHYSICAL,
            description="Footprints matching Alex's shoes found near broken window",
            source="crime_scene_investigation",
            supports=["F001", "F002"],
            contradicts=[],
            reliability=0.90,
            metadata={
                "collected_by": "CSI Team",
                "date": "2024-01-16",
            },
        ),
        Evidence(
            evidence_id="E003",
            type=EvidenceType.PHYSICAL,
            description="Metal baseball bat with blood matching Alex's DNA",
            source="crime_scene_investigation",
            supports=["F005"],
            contradicts=[],
            reliability=0.98,
            metadata={
                "collected_by": "CSI Team",
                "date": "2024-01-16",
                "location": "living_room",
            },
        ),
        Evidence(
            evidence_id="E004",
            type=EvidenceType.FORENSIC,
            description="Medical examination report showing Alex sustained broken ribs, head trauma, and severe bruising",
            source="hospital_records",
            supports=["F006"],
            contradicts=[],
            reliability=0.99,
            metadata={
                "examined_by": "Dr. Sarah Johnson",
                "date": "2024-01-16",
                "hospital": "Arandia General Hospital",
            },
        ),
        Evidence(
            evidence_id="E005",
            type=EvidenceType.DIGITAL,
            description="911 call recording from David reporting an intruder",
            source="emergency_services",
            supports=["F007"],
            contradicts=[],
            reliability=1.0,
            metadata={
                "call_time": "2024-01-15T23:52:00",
                "duration": "3:42",
            },
        ),
        Evidence(
            evidence_id="E006",
            type=EvidenceType.TESTIMONIAL,
            description="Neighbor heard shouting and sounds of a struggle around 11:45 PM",
            source="W002",
            supports=["F003"],
            contradicts=[],
            reliability=0.70,
            metadata={
                "witness": "W002",
                "distance_from_scene": "next_door",
            },
        ),
        Evidence(
            evidence_id="E007",
            type=EvidenceType.FORENSIC,
            description="No defensive wounds found on David during examination",
            source="medical_examination",
            supports=[],
            contradicts=["F004"],
            reliability=0.85,
            metadata={
                "examined_by": "Dr. Michael Chen",
                "date": "2024-01-16",
            },
        ),
        Evidence(
            evidence_id="E008",
            type=EvidenceType.PHYSICAL,
            description="No weapons found on Alex or at the scene belonging to Alex",
            source="police_search",
            supports=["F008"],
            contradicts=[],
            reliability=0.95,
            metadata={
                "searched_by": "Officer Martinez",
                "date": "2024-01-16",
            },
        ),
    ]

    # Witnesses
    witnesses = [
        Witness(
            witness_id="W001",
            name="David Thompson",
            statement="I was sleeping when I heard glass breaking downstairs. I went to investigate and found an intruder in my house. He came at me aggressively, so I grabbed my baseball bat and defended myself. I was terrified for my life.",
            reliability_factors={
                "bias": "victim_and_defendant_in_related_charge",
                "opportunity_to_observe": "high",
                "memory_quality": "good",
                "consistency": "statement_consistent",
                "personal_interest": "high",
            },
            related_evidence=["E001", "E003", "E005"],
            metadata={
                "interviewed_date": "2024-01-16",
                "interviewed_by": "Detective Williams",
            },
        ),
        Witness(
            witness_id="W002",
            name="Margaret Foster",
            statement="I live next door. I heard loud noises and shouting around 11:45 PM. I couldn't make out words, but it sounded like two men arguing or fighting. Then it went quiet for a few minutes before I heard sirens.",
            reliability_factors={
                "bias": "none_apparent",
                "opportunity_to_observe": "moderate",
                "memory_quality": "good",
                "consistency": "statement_consistent",
                "personal_interest": "none",
            },
            related_evidence=["E006"],
            metadata={
                "interviewed_date": "2024-01-16",
                "interviewed_by": "Officer Martinez",
            },
        ),
        Witness(
            witness_id="W003",
            name="Alex Johnson",
            statement="I made a mistake entering the house - I thought it was my friend's place because I was confused about the address. When David confronted me, I tried to explain, but he immediately attacked me with a bat without giving me a chance to leave. I put my hands up, but he just kept hitting me. I never attacked him.",
            reliability_factors={
                "bias": "defendant_in_case",
                "opportunity_to_observe": "high",
                "memory_quality": "potentially_impaired_by_trauma",
                "consistency": "conflicts_with_other_evidence",
                "personal_interest": "very_high",
            },
            related_evidence=["E004"],
            metadata={
                "interviewed_date": "2024-01-17",
                "interviewed_by": "Detective Williams",
                "note": "Interviewed after medical treatment",
            },
        ),
    ]

    # Create the case
    case = Case(
        case_id="CASE_001",
        title="The Night Intruder",
        description="Alex Johnson is charged with burglary and assault after entering David Thompson's home without permission at 11:45 PM. David Thompson struck Alex with a baseball bat, causing serious injuries. David claims self-defense. Alex claims he entered by mistake and was attacked without provocation. The case involves questions about burglary, assault, self-defense, necessity, proportionality, and excessive force.",
        jurisdiction="Republic of Arandia",
        case_type=CaseType.CRIMINAL,
        defendant="Alex Johnson",
        prosecution="The People of Arandia",
        facts=facts,
        evidence=evidence,
        witnesses=witnesses,
        charges=["burglary", "assault"],
        applicable_laws=["LAW_101", "LAW_102", "LAW_104", "LAW_201", "LAW_202"],
        status=CaseStatus.INITIALIZED,
        created_at=datetime(2024, 1, 16, 10, 0, 0),
        updated_at=datetime(2024, 1, 16, 10, 0, 0),
        metadata={
            "incident_date": "2024-01-15T23:45:00",
            "incident_location": "123 Oak Street, Arandia City",
            "arresting_officer": "Officer Martinez",
            "key_issues": [
                "unauthorized_entry",
                "self_defense_claim",
                "proportionality_of_force",
                "reasonable_belief_of_threat",
            ],
        },
    )

    return case


def get_all_cases() -> List[Case]:
    """Get all seed cases"""
    return [
        get_case_001(),
        # Additional cases will be added in future iterations
    ]


def get_case_by_id(case_id: str) -> Case | None:
    """Get a specific case by ID"""
    cases = get_all_cases()
    for case in cases:
        if case.case_id == case_id:
            return case
    return None
