"""Element binding seed data

Bindings link the facts and evidence of a case to individual conditions of
the legal rules. They are authored from the case file - they state only
*which* material bears on an element, never whether the element holds. The
rule engine decides that.

Note that CASE_001 involves conduct by two parties, so bindings carry a
``subject``: the same assault rule is evaluated separately for the charge
against Alex Johnson and for David Thompson's use of force.
"""

from typing import List

from app.domain import BindingStance, ElementBinding

ALEX = "Alex Johnson"
DAVID = "David Thompson"


def _binding(
    binding_id: str,
    rule_id: str,
    condition_id: str,
    subject: str,
    stance: BindingStance,
    note: str,
    fact_ids: List[str] | None = None,
    evidence_ids: List[str] | None = None,
) -> ElementBinding:
    """Build a CASE_001 binding with the shared defaults filled in"""
    return ElementBinding(
        binding_id=binding_id,
        case_id="CASE_001",
        rule_id=rule_id,
        condition_id=condition_id,
        subject=subject,
        stance=stance,
        fact_ids=fact_ids or [],
        evidence_ids=evidence_ids or [],
        note=note,
        source="case_file",
    )


def get_case_001_bindings() -> List[ElementBinding]:
    """Element bindings for CASE_001 - The Night Intruder

    Deliberately incomplete where the case record is incomplete: LAW_104's
    intent element has no binding at all, because nothing in the evidence
    speaks to what Alex intended to do inside the house.
    """
    return [
        # ------------------------------------------------------------------
        # LAW_104 Burglary - charge against Alex Johnson
        # ------------------------------------------------------------------
        _binding(
            "B001",
            "LAW_104",
            "C1",
            ALEX,
            BindingStance.SUPPORTS,
            "Entry through a broken kitchen window at 11:45 PM without permission",
            fact_ids=["F001", "F002"],
            evidence_ids=["E001", "E002"],
        ),
        # LAW_104 C2 (intent to commit an offence inside) is intentionally
        # unbound: no evidence in the record speaks to Alex's intent.
        # ------------------------------------------------------------------
        # LAW_101 Assault - charge against Alex Johnson
        # ------------------------------------------------------------------
        _binding(
            "B002",
            "LAW_101",
            "C1",
            ALEX,
            BindingStance.SUPPORTS,
            "David's account that Alex came at him, and the neighbour hearing a struggle",
            fact_ids=["F004"],
            evidence_ids=["E006"],
        ),
        _binding(
            "B003",
            "LAW_101",
            "C1",
            ALEX,
            BindingStance.CONTRADICTS,
            "No defensive wounds were found on David",
            evidence_ids=["E007"],
        ),
        _binding(
            "B004",
            "LAW_101",
            "C2",
            ALEX,
            BindingStance.SUPPORTS,
            "Contact is alleged only through the disputed account of the attack",
            fact_ids=["F004"],
        ),
        _binding(
            "B005",
            "LAW_101",
            "C2",
            ALEX,
            BindingStance.CONTRADICTS,
            "Absence of defensive wounds on David is inconsistent with a physical attack",
            evidence_ids=["E007"],
        ),
        _binding(
            "B006",
            "LAW_101",
            "C3",
            ALEX,
            BindingStance.SUPPORTS,
            "Any force used by an unlawful intruder would itself be unlawful",
            fact_ids=["F001"],
            evidence_ids=["E001"],
        ),
        # ------------------------------------------------------------------
        # LAW_101 Assault - David Thompson's use of force
        # ------------------------------------------------------------------
        _binding(
            "B007",
            "LAW_101",
            "C1",
            DAVID,
            BindingStance.SUPPORTS,
            "David struck Alex with a metal bat; the bat carries Alex's blood",
            fact_ids=["F005"],
            evidence_ids=["E003"],
        ),
        _binding(
            "B008",
            "LAW_101",
            "C2",
            DAVID,
            BindingStance.SUPPORTS,
            "Contact is established by the injuries and the blood on the bat",
            fact_ids=["F005", "F006"],
            evidence_ids=["E003", "E004"],
        ),
        _binding(
            "B009",
            "LAW_101",
            "C3",
            DAVID,
            BindingStance.SUPPORTS,
            "Alex was unarmed, so the force was not obviously lawful",
            fact_ids=["F008"],
            evidence_ids=["E008"],
        ),
        _binding(
            "B010",
            "LAW_101",
            "C3",
            DAVID,
            BindingStance.CONTRADICTS,
            "If Alex attacked first, David's force may have been lawful",
            fact_ids=["F004"],
        ),
        # ------------------------------------------------------------------
        # LAW_102 Aggravated Assault - David Thompson
        # C1 is determined by LAW_101 for the same subject.
        # ------------------------------------------------------------------
        _binding(
            "B011",
            "LAW_102",
            "C2",
            DAVID,
            BindingStance.SUPPORTS,
            "Medical report records broken ribs and head trauma",
            fact_ids=["F006"],
            evidence_ids=["E004"],
        ),
        # ------------------------------------------------------------------
        # LAW_201 Self Defense - David Thompson
        # ------------------------------------------------------------------
        _binding(
            "B012",
            "LAW_201",
            "C1",
            DAVID,
            BindingStance.SUPPORTS,
            "A stranger had broken into the house at night and was confronted inside",
            fact_ids=["F001", "F003"],
            evidence_ids=["E001", "E005", "E006"],
        ),
        _binding(
            "B013",
            "LAW_201",
            "C2",
            DAVID,
            BindingStance.SUPPORTS,
            "Necessity rests on the disputed claim that Alex attacked first",
            fact_ids=["F004"],
        ),
        _binding(
            "B014",
            "LAW_201",
            "C2",
            DAVID,
            BindingStance.CONTRADICTS,
            "Alex was unarmed and no weapon was found at the scene",
            fact_ids=["F008"],
            evidence_ids=["E008"],
        ),
        _binding(
            "B015",
            "LAW_201",
            "C3",
            DAVID,
            BindingStance.CONTRADICTS,
            "Repeated blows with a metal bat against an unarmed person caused serious injury",
            fact_ids=["F006", "F008"],
            evidence_ids=["E004", "E008"],
        ),
        # ------------------------------------------------------------------
        # LAW_202 Excessive Defensive Force - David Thompson
        # ------------------------------------------------------------------
        _binding(
            "B016",
            "LAW_202",
            "C1",
            DAVID,
            BindingStance.SUPPORTS,
            "David used force with a metal bat",
            fact_ids=["F005"],
            evidence_ids=["E003"],
        ),
        _binding(
            "B017",
            "LAW_202",
            "C2",
            DAVID,
            BindingStance.SUPPORTS,
            "Serious injuries inflicted on an unarmed person",
            fact_ids=["F006", "F008"],
            evidence_ids=["E004", "E008"],
        ),
        _binding(
            "B018",
            "LAW_202",
            "C2",
            DAVID,
            BindingStance.CONTRADICTS,
            "If Alex attacked first, the threat may have matched the force used",
            fact_ids=["F004"],
        ),
    ]


def get_bindings_for_case(case_id: str) -> List[ElementBinding]:
    """Element bindings for a case, or an empty list if none are seeded"""
    if case_id == "CASE_001":
        return get_case_001_bindings()
    return []
