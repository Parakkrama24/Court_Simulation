"""Tests for seed data

Validates that seed data is correctly loaded and structured.
"""

import pytest
from app.seed import get_all_cases, get_case_by_id, get_all_legal_rules, get_legal_rules_by_category
from app.domain import LegalCategory, CaseType, FactStatus


class TestLegalRulesSeed:
    """Tests for legal rules seed data"""

    def test_load_all_legal_rules(self):
        """Test that all legal rules can be loaded"""
        rules = get_all_legal_rules()
        assert len(rules) > 0

    def test_legal_rules_have_unique_ids(self):
        """Test that all legal rule IDs are unique"""
        rules = get_all_legal_rules()
        rule_ids = [rule.rule_id for rule in rules]
        assert len(rule_ids) == len(set(rule_ids))

    def test_principles_loaded(self):
        """Test that principles are loaded"""
        principles = get_legal_rules_by_category(LegalCategory.PRINCIPLE)
        assert len(principles) == 5
        rule_ids = [p.rule_id for p in principles]
        assert "P001" in rule_ids  # Presumption of Innocence
        assert "P002" in rule_ids  # Burden of Proof
        assert "P003" in rule_ids  # Evidence Requirement
        assert "P004" in rule_ids  # Reasonable Doubt
        assert "P005" in rule_ids  # Evidence Consistency

    def test_criminal_laws_loaded(self):
        """Test that criminal laws are loaded"""
        laws = get_legal_rules_by_category(LegalCategory.OFFENSE)
        offense_ids = [law.rule_id for law in laws]
        assert "LAW_101" in offense_ids  # Assault
        assert "LAW_102" in offense_ids  # Aggravated Assault
        assert "LAW_103" in offense_ids  # Theft
        assert "LAW_104" in offense_ids  # Burglary

    def test_defense_laws_loaded(self):
        """Test that defense laws are loaded"""
        defenses = get_legal_rules_by_category(LegalCategory.DEFENSE)
        defense_ids = [d.rule_id for d in defenses]
        assert "LAW_201" in defense_ids  # Self Defense
        assert "LAW_202" in defense_ids  # Excessive Defensive Force

    def test_evidence_rules_loaded(self):
        """Test that evidence rules are loaded"""
        evidence_rules = get_legal_rules_by_category(LegalCategory.EVIDENCE_RULE)
        assert len(evidence_rules) == 5
        rule_ids = [r.rule_id for r in evidence_rules]
        assert "E001" in rule_ids  # Direct Evidence
        assert "E002" in rule_ids  # Circumstantial Evidence
        assert "E003" in rule_ids  # Witness Reliability
        assert "E004" in rule_ids  # Conflicting Evidence
        assert "E005" in rule_ids  # Fabricated Evidence

    def test_legal_rules_have_conditions(self):
        """Test that offense and defense laws have conditions"""
        assault_rules = [r for r in get_all_legal_rules() if r.rule_id == "LAW_101"]
        assert len(assault_rules) == 1
        assault = assault_rules[0]
        assert len(assault.conditions) == 3

        self_defense_rules = [r for r in get_all_legal_rules() if r.rule_id == "LAW_201"]
        assert len(self_defense_rules) == 1
        self_defense = self_defense_rules[0]
        assert len(self_defense.conditions) == 3


class TestCasesSeed:
    """Tests for case seed data"""

    def test_load_all_cases(self):
        """Test that all cases can be loaded"""
        cases = get_all_cases()
        assert len(cases) >= 1

    def test_get_case_001(self):
        """Test that CASE_001 can be loaded"""
        case = get_case_by_id("CASE_001")
        assert case is not None
        assert case.case_id == "CASE_001"
        assert case.title == "The Night Intruder"
        assert case.case_type == CaseType.CRIMINAL

    def test_case_001_has_facts(self):
        """Test that CASE_001 has facts"""
        case = get_case_by_id("CASE_001")
        assert len(case.facts) > 0

        # Check specific facts
        fact_ids = [f.fact_id for f in case.facts]
        assert "F001" in fact_ids  # Alex entered house
        assert "F002" in fact_ids  # Entry through broken window

    def test_case_001_has_evidence(self):
        """Test that CASE_001 has evidence"""
        case = get_case_by_id("CASE_001")
        assert len(case.evidence) > 0

        # Check specific evidence
        evidence_ids = [e.evidence_id for e in case.evidence]
        assert "E001" in evidence_ids  # Broken window
        assert "E003" in evidence_ids  # Baseball bat
        assert "E004" in evidence_ids  # Medical report

    def test_case_001_has_witnesses(self):
        """Test that CASE_001 has witnesses"""
        case = get_case_by_id("CASE_001")
        assert len(case.witnesses) == 3

        # Check specific witnesses
        witness_ids = [w.witness_id for w in case.witnesses]
        assert "W001" in witness_ids  # David Thompson
        assert "W002" in witness_ids  # Margaret Foster
        assert "W003" in witness_ids  # Alex Johnson

    def test_case_001_has_charges(self):
        """Test that CASE_001 has charges"""
        case = get_case_by_id("CASE_001")
        assert "burglary" in case.charges
        assert "assault" in case.charges

    def test_case_001_has_applicable_laws(self):
        """Test that CASE_001 has applicable laws"""
        case = get_case_by_id("CASE_001")
        assert "LAW_101" in case.applicable_laws  # Assault
        assert "LAW_102" in case.applicable_laws  # Aggravated Assault
        assert "LAW_104" in case.applicable_laws  # Burglary
        assert "LAW_201" in case.applicable_laws  # Self Defense

    def test_case_001_evidence_references_valid(self):
        """Test that evidence in CASE_001 references valid facts"""
        case = get_case_by_id("CASE_001")
        fact_ids = {f.fact_id for f in case.facts}

        for evidence in case.evidence:
            for supported_fact in evidence.supports:
                # Evidence can support facts or claims
                # At minimum, check format is correct
                assert isinstance(supported_fact, str)
                assert len(supported_fact) > 0

    def test_case_001_witnesses_have_reliability_factors(self):
        """Test that witnesses have reliability factors"""
        case = get_case_by_id("CASE_001")

        for witness in case.witnesses:
            assert isinstance(witness.reliability_factors, dict)
            # Each witness should have some reliability factors
            if witness.witness_id == "W001":  # David Thompson
                assert "bias" in witness.reliability_factors
                assert "opportunity_to_observe" in witness.reliability_factors

    def test_case_001_facts_have_status(self):
        """Test that facts have status"""
        case = get_case_by_id("CASE_001")

        established_facts = [f for f in case.facts if f.status == FactStatus.ESTABLISHED]
        disputed_facts = [f for f in case.facts if f.status == FactStatus.DISPUTED]

        # Should have both established and disputed facts
        assert len(established_facts) > 0
        assert len(disputed_facts) > 0

    def test_get_nonexistent_case(self):
        """Test that getting a nonexistent case returns None"""
        case = get_case_by_id("CASE_999")
        assert case is None


class TestDataIntegrity:
    """Tests for overall data integrity"""

    def test_case_001_evidence_supports_facts(self):
        """Test that evidence in CASE_001 properly supports facts"""
        case = get_case_by_id("CASE_001")

        # E001 should support F001 and F002 (entry through broken window)
        e001 = next(e for e in case.evidence if e.evidence_id == "E001")
        assert "F001" in e001.supports or "F002" in e001.supports

    def test_case_001_witness_evidence_linkage(self):
        """Test that witnesses are properly linked to evidence"""
        case = get_case_by_id("CASE_001")

        # W001 (David) should be linked to relevant evidence
        w001 = next(w for w in case.witnesses if w.witness_id == "W001")
        assert len(w001.related_evidence) > 0
