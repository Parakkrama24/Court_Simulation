"""Tests for domain models

Validates that all Pydantic models work correctly and enforce constraints.
"""

import pytest
from datetime import datetime
from app.domain import (
    Fact,
    FactStatus,
    Evidence,
    EvidenceType,
    Witness,
    Condition,
    LegalRule,
    LegalCategory,
    Argument,
    Verdict,
    AuditReport,
    Case,
    CaseStatus,
    CaseType,
)


class TestFact:
    """Tests for Fact model"""

    def test_create_fact(self):
        """Test creating a fact with required fields"""
        fact = Fact(
            fact_id="F001",
            description="Test fact",
            source="test_source",
        )
        assert fact.fact_id == "F001"
        assert fact.description == "Test fact"
        assert fact.source == "test_source"
        assert fact.status == FactStatus.UNKNOWN  # default

    def test_fact_with_status(self):
        """Test creating a fact with specific status"""
        fact = Fact(
            fact_id="F002",
            description="Established fact",
            source="evidence",
            status=FactStatus.ESTABLISHED,
        )
        assert fact.status == FactStatus.ESTABLISHED

    def test_fact_with_metadata(self):
        """Test creating a fact with metadata"""
        metadata = {"timestamp": "2024-01-15T23:45:00"}
        fact = Fact(
            fact_id="F003",
            description="Fact with metadata",
            source="witness",
            metadata=metadata,
        )
        assert fact.metadata == metadata


class TestEvidence:
    """Tests for Evidence model"""

    def test_create_evidence(self):
        """Test creating evidence with required fields"""
        evidence = Evidence(
            evidence_id="E001",
            type=EvidenceType.PHYSICAL,
            description="Physical evidence",
            source="crime_scene",
        )
        assert evidence.evidence_id == "E001"
        assert evidence.type == EvidenceType.PHYSICAL
        assert evidence.reliability == 1.0  # default

    def test_evidence_reliability_validation(self):
        """Test that reliability is bounded between 0.0 and 1.0"""
        evidence = Evidence(
            evidence_id="E002",
            type=EvidenceType.TESTIMONIAL,
            description="Testimony",
            source="witness",
            reliability=0.75,
        )
        assert evidence.reliability == 0.75

    def test_evidence_supports_contradicts(self):
        """Test evidence with supports and contradicts lists"""
        evidence = Evidence(
            evidence_id="E003",
            type=EvidenceType.FORENSIC,
            description="DNA evidence",
            source="lab",
            supports=["F001", "F002"],
            contradicts=["F003"],
        )
        assert len(evidence.supports) == 2
        assert len(evidence.contradicts) == 1


class TestWitness:
    """Tests for Witness model"""

    def test_create_witness(self):
        """Test creating a witness"""
        witness = Witness(
            witness_id="W001",
            name="John Doe",
            statement="I saw something happen",
        )
        assert witness.witness_id == "W001"
        assert witness.name == "John Doe"
        assert len(witness.related_evidence) == 0  # default

    def test_witness_with_reliability_factors(self):
        """Test witness with reliability factors"""
        factors = {
            "bias": "none",
            "opportunity_to_observe": "high",
        }
        witness = Witness(
            witness_id="W002",
            name="Jane Smith",
            statement="I witnessed the event",
            reliability_factors=factors,
        )
        assert witness.reliability_factors == factors


class TestLegalRule:
    """Tests for LegalRule model"""

    def test_create_legal_rule(self):
        """Test creating a legal rule"""
        rule = LegalRule(
            rule_id="LAW_001",
            name="Test Law",
            category=LegalCategory.OFFENSE,
            description="A test law",
            effect="test_effect",
        )
        assert rule.rule_id == "LAW_001"
        assert rule.category == LegalCategory.OFFENSE
        assert rule.jurisdiction == "Republic of Arandia"  # default

    def test_legal_rule_with_conditions(self):
        """Test legal rule with conditions"""
        conditions = [
            Condition(id="C1", description="Condition 1", required=True),
            Condition(id="C2", description="Condition 2", required=False),
        ]
        rule = LegalRule(
            rule_id="LAW_002",
            name="Law with conditions",
            category=LegalCategory.DEFENSE,
            description="A law with conditions",
            conditions=conditions,
            effect="defense_applies",
        )
        assert len(rule.conditions) == 2
        assert rule.conditions[0].required is True
        assert rule.conditions[1].required is False


class TestArgument:
    """Tests for Argument model"""

    def test_create_argument(self):
        """Test creating an argument"""
        argument = Argument(
            argument_id="ARG001",
            agent_id="prosecution",
            claim="Test claim",
            reasoning="Test reasoning",
        )
        assert argument.argument_id == "ARG001"
        assert argument.confidence == 0.5  # default

    def test_argument_with_references(self):
        """Test argument with evidence and law references"""
        argument = Argument(
            argument_id="ARG002",
            agent_id="defense",
            claim="Defense claim",
            evidence_ids=["E001", "E002"],
            law_ids=["LAW_201"],
            reasoning="Defense reasoning",
            confidence=0.8,
        )
        assert len(argument.evidence_ids) == 2
        assert len(argument.law_ids) == 1
        assert argument.confidence == 0.8


class TestVerdict:
    """Tests for Verdict model"""

    def test_create_verdict(self):
        """Test creating a verdict"""
        verdict = Verdict(
            verdict_id="V001",
            case_id="CASE_001",
            agent_id="judge",
            charges=["assault"],
            decision="not_guilty",
            reasoning="Insufficient evidence",
        )
        assert verdict.verdict_id == "V001"
        assert verdict.decision == "not_guilty"

    def test_verdict_with_references(self):
        """Test verdict with evidence and law references"""
        verdict = Verdict(
            verdict_id="V002",
            case_id="CASE_001",
            agent_id="jury_1",
            charges=["burglary", "assault"],
            decision="guilty",
            reasoning="Evidence clearly establishes guilt",
            evidence_used=["E001", "E002", "E003"],
            laws_used=["LAW_101", "LAW_104"],
            confidence=0.9,
        )
        assert len(verdict.evidence_used) == 3
        assert len(verdict.laws_used) == 2


class TestAuditReport:
    """Tests for AuditReport model"""

    def test_create_audit_report(self):
        """Test creating an audit report"""
        report = AuditReport(
            audit_id="AUD001",
            case_id="CASE_001",
            final_assessment="No violations detected",
        )
        assert report.audit_id == "AUD001"
        assert len(report.hallucinations) == 0  # default

    def test_audit_report_with_violations(self):
        """Test audit report with violations"""
        report = AuditReport(
            audit_id="AUD002",
            case_id="CASE_001",
            evidence_violations=[
                {"agent": "prosecution", "violation": "Referenced invalid evidence ID"}
            ],
            hallucinations=[
                {"agent": "defense", "type": "invented_fact", "description": "Claimed fact not in case"}
            ],
            final_assessment="Multiple violations detected",
        )
        assert len(report.evidence_violations) == 1
        assert len(report.hallucinations) == 1


class TestCase:
    """Tests for Case model"""

    def test_create_case(self):
        """Test creating a case with required fields"""
        case = Case(
            case_id="CASE_001",
            title="Test Case",
            description="A test case",
            case_type=CaseType.CRIMINAL,
            defendant="John Doe",
        )
        assert case.case_id == "CASE_001"
        assert case.case_type == CaseType.CRIMINAL
        assert case.status == CaseStatus.INITIALIZED  # default
        assert case.jurisdiction == "Republic of Arandia"  # default

    def test_case_with_all_components(self):
        """Test creating a case with facts, evidence, and witnesses"""
        facts = [
            Fact(fact_id="F001", description="Fact 1", source="source1"),
            Fact(fact_id="F002", description="Fact 2", source="source2"),
        ]
        evidence = [
            Evidence(
                evidence_id="E001",
                type=EvidenceType.PHYSICAL,
                description="Evidence 1",
                source="crime_scene",
            )
        ]
        witnesses = [Witness(witness_id="W001", name="Witness 1", statement="I saw it")]

        case = Case(
            case_id="CASE_002",
            title="Complete Case",
            description="Case with all components",
            case_type=CaseType.CRIMINAL,
            defendant="Jane Smith",
            facts=facts,
            evidence=evidence,
            witnesses=witnesses,
            charges=["assault", "burglary"],
            applicable_laws=["LAW_101", "LAW_104"],
        )

        assert len(case.facts) == 2
        assert len(case.evidence) == 1
        assert len(case.witnesses) == 1
        assert len(case.charges) == 2
        assert len(case.applicable_laws) == 2
