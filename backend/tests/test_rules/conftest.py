"""Shared fixtures for rule engine tests

The synthetic case and rule set keep engine tests independent of the seed
data, so changing CASE_001 cannot silently change what these tests assert.
"""

import pytest

from app.domain import (
    BindingStance,
    Case,
    CaseType,
    Condition,
    ElementBinding,
    Evidence,
    EvidenceType,
    Fact,
    FactStatus,
    LegalCategory,
    LegalRule,
    Witness,
)
from app.rules import LegalRuleRegistry

TEST_CASE_ID = "CASE_TEST"
SUBJECT = "Test Defendant"


@pytest.fixture
def case() -> Case:
    """A small case with one fact per status and one evidence item per weight"""
    return Case(
        case_id=TEST_CASE_ID,
        title="Synthetic Case",
        description="Fixture case for rule engine tests",
        case_type=CaseType.CRIMINAL,
        defendant=SUBJECT,
        facts=[
            Fact(
                fact_id="F1",
                description="Established fact",
                source="case_file",
                status=FactStatus.ESTABLISHED,
            ),
            Fact(
                fact_id="F2",
                description="Disputed fact",
                source="case_file",
                status=FactStatus.DISPUTED,
            ),
            Fact(
                fact_id="F3",
                description="Unknown fact",
                source="case_file",
                status=FactStatus.UNKNOWN,
            ),
        ],
        evidence=[
            Evidence(
                evidence_id="EV1",
                type=EvidenceType.PHYSICAL,
                description="Reliable physical evidence",
                source="crime_scene",
                supports=["F1"],
                reliability=0.9,
            ),
            Evidence(
                evidence_id="EV2",
                type=EvidenceType.TESTIMONIAL,
                description="Testimony of moderate reliability",
                source="WT1",
                supports=["F2"],
                reliability=0.6,
            ),
            Evidence(
                evidence_id="EV3",
                type=EvidenceType.CIRCUMSTANTIAL,
                description="Weak circumstantial evidence",
                source="investigation",
                contradicts=["F2"],
                reliability=0.5,
            ),
        ],
        witnesses=[
            Witness(
                witness_id="WT1",
                name="Reliable Witness",
                statement="I saw it happen from close range.",
                reliability_factors={
                    "bias": "none_apparent",
                    "opportunity_to_observe": "high",
                    "memory_quality": "good",
                    "consistency": "statement_consistent",
                    "personal_interest": "none",
                },
                related_evidence=["EV2"],
            )
        ],
        charges=["test_offense"],
        applicable_laws=["RULE_A", "RULE_B", "RULE_C"],
    )


@pytest.fixture
def rules() -> list[LegalRule]:
    """Synthetic rules covering each structural case the engine must handle"""
    return [
        LegalRule(
            rule_id="RULE_A",
            name="Two Element Offense",
            category=LegalCategory.OFFENSE,
            description="Requires two elements",
            conditions=[
                Condition(id="C1", description="First element"),
                Condition(id="C2", description="Second element"),
            ],
            effect="rule_a_established",
        ),
        LegalRule(
            rule_id="RULE_B",
            name="Dependent Offense",
            category=LegalCategory.OFFENSE,
            description="Builds on RULE_A",
            conditions=[
                Condition(id="C1", description="RULE_A is established", depends_on_rule="RULE_A"),
                Condition(id="C2", description="Aggravating element"),
            ],
            effect="rule_b_established",
        ),
        LegalRule(
            rule_id="RULE_C",
            name="Unconditional Principle",
            category=LegalCategory.PRINCIPLE,
            description="Applies without conditions",
            conditions=[],
            effect="rule_c_applies",
        ),
        LegalRule(
            rule_id="RULE_OPT",
            name="Optional Conditions Only",
            category=LegalCategory.EVIDENCE_RULE,
            description="All conditions optional",
            conditions=[
                Condition(id="C1", description="First factor", required=False),
                Condition(id="C2", description="Second factor", required=False),
            ],
            effect="factors_considered",
        ),
        LegalRule(
            rule_id="RULE_CYC1",
            name="Cyclic Rule One",
            category=LegalCategory.OFFENSE,
            description="Depends on RULE_CYC2",
            conditions=[
                Condition(id="C1", description="Depends on two", depends_on_rule="RULE_CYC2")
            ],
            effect="cyc1",
        ),
        LegalRule(
            rule_id="RULE_CYC2",
            name="Cyclic Rule Two",
            category=LegalCategory.OFFENSE,
            description="Depends on RULE_CYC1",
            conditions=[
                Condition(id="C1", description="Depends on one", depends_on_rule="RULE_CYC1")
            ],
            effect="cyc2",
        ),
        LegalRule(
            rule_id="RULE_MISSING_DEP",
            name="Broken Dependency",
            category=LegalCategory.OFFENSE,
            description="Depends on a rule that does not exist",
            conditions=[
                Condition(id="C1", description="Depends on nothing", depends_on_rule="RULE_NOPE")
            ],
            effect="never",
        ),
    ]


@pytest.fixture
def registry(rules: list[LegalRule]) -> LegalRuleRegistry:
    """Registry over the synthetic rules"""
    return LegalRuleRegistry(rules)


def binding(
    rule_id: str,
    condition_id: str,
    stance: BindingStance = BindingStance.SUPPORTS,
    fact_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    subject: str = SUBJECT,
    binding_id: str = "B",
    case_id: str = TEST_CASE_ID,
) -> ElementBinding:
    """Build a binding for the synthetic case"""
    return ElementBinding(
        binding_id=binding_id,
        case_id=case_id,
        rule_id=rule_id,
        condition_id=condition_id,
        subject=subject,
        stance=stance,
        fact_ids=fact_ids or [],
        evidence_ids=evidence_ids or [],
    )
