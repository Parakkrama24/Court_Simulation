"""Tests for reference validation (hallucination prevention)"""

from app.domain import Argument, BindingStance, Case, Verdict
from app.rules import LegalRuleRegistry, ReferenceType, ReferenceValidator

from .conftest import SUBJECT, binding


def make_argument(evidence_ids=None, law_ids=None, counter_ids=None) -> Argument:
    return Argument(
        argument_id="ARG1",
        agent_id="prosecution_agent",
        claim="The defendant committed the offense",
        evidence_ids=evidence_ids or [],
        law_ids=law_ids or [],
        counter_argument_ids=counter_ids or [],
        reasoning="Because of the cited evidence",
    )


class TestPrimitiveChecks:
    """Existence checks for each reference type"""

    def test_known_references_exist(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        assert validator.evidence_exists("EV1")
        assert validator.fact_exists("F1")
        assert validator.witness_exists("WT1")
        assert validator.law_exists("RULE_A")

    def test_unknown_references_do_not_exist(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        assert not validator.evidence_exists("E999")
        assert not validator.fact_exists("F999")
        assert not validator.witness_exists("W999")
        assert not validator.law_exists("RULE_NOPE")


class TestArgumentValidation:
    """Arguments may only cite real evidence and real laws"""

    def test_valid_argument_passes(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_argument(make_argument(["EV1"], ["RULE_A"]))
        assert result.valid
        assert bool(result) is True
        assert result.errors == []
        assert result.checked_references == 2

    def test_fabricated_evidence_is_rejected(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_argument(make_argument(["EV1", "E999"], ["RULE_A"]))
        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0].reference_type == ReferenceType.EVIDENCE
        assert result.errors[0].reference_id == "E999"
        assert "ARG1" in result.errors[0].location

    def test_fabricated_law_is_rejected(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_argument(make_argument(["EV1"], ["LAW_999"]))
        assert not result.valid
        assert result.errors[0].reference_type == ReferenceType.LAW

    def test_unknown_counter_argument_is_rejected(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_argument(
            make_argument(["EV1"], ["RULE_A"], ["ARG_MISSING"]), known_argument_ids=["ARG0"]
        )
        assert not result.valid
        assert result.errors[0].reference_type == ReferenceType.ARGUMENT

    def test_messages_are_usable_for_regeneration(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_argument(make_argument(["E999"]))
        assert result.messages
        assert "E999" in result.messages[0]
        assert case.case_id in result.messages[0]

    def test_errors_convert_to_audit_violations(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_argument(make_argument(["E999"]))
        violations = result.as_violations(agent_id="prosecution_agent", case_id=case.case_id)
        assert violations[0]["agent_id"] == "prosecution_agent"
        assert violations[0]["reference_id"] == "E999"
        assert violations[0]["detected_at"]


class TestVerdictValidation:
    """Verdicts must rely on real evidence, laws, and the right case"""

    def _verdict(self, case_id: str, evidence_used=None, laws_used=None) -> Verdict:
        return Verdict(
            verdict_id="V1",
            case_id=case_id,
            agent_id="judge_agent",
            charges=["test_offense"],
            decision="not_guilty",
            reasoning="Reasonable doubt remains",
            evidence_used=evidence_used or [],
            laws_used=laws_used or [],
        )

    def test_valid_verdict_passes(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_verdict(self._verdict(case.case_id, ["EV1"], ["RULE_A"]))
        assert result.valid

    def test_invalid_evidence_is_rejected(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_verdict(self._verdict(case.case_id, ["E999"]))
        assert not result.valid

    def test_wrong_case_is_rejected(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_verdict(self._verdict("CASE_OTHER", ["EV1"]))
        assert not result.valid
        assert "CASE_OTHER" in result.errors[0].message


class TestBindingValidation:
    """Bindings must target a real rule condition and cite real material"""

    def test_valid_binding_passes(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_binding(binding("RULE_A", "C1", fact_ids=["F1"]))
        assert result.valid

    def test_unknown_condition_is_rejected(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_binding(binding("RULE_A", "C9", fact_ids=["F1"]))
        assert not result.valid
        assert result.errors[0].reference_type == ReferenceType.CONDITION

    def test_unknown_rule_is_rejected(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_binding(binding("RULE_NOPE", "C1", fact_ids=["F1"]))
        assert not result.valid
        assert result.errors[0].reference_type == ReferenceType.LAW

    def test_empty_binding_is_rejected(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_binding(binding("RULE_A", "C1"))
        assert not result.valid
        assert "neither a fact nor evidence" in result.errors[0].message

    def test_bindings_are_validated_as_a_batch(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_bindings(
            [
                binding("RULE_A", "C1", fact_ids=["F1"]),
                binding("RULE_A", "C2", BindingStance.CONTRADICTS, evidence_ids=["E999"]),
                binding("RULE_NOPE", "C1", fact_ids=["F1"]),
            ]
        )
        assert not result.valid
        assert len(result.errors) == 2

    def test_subject_is_free_text_and_not_validated(self, case: Case, registry: LegalRuleRegistry):
        validator = ReferenceValidator(case, registry)
        result = validator.validate_binding(
            binding("RULE_A", "C1", fact_ids=["F1"], subject=f"{SUBJECT} (alias)")
        )
        assert result.valid
