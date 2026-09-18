"""Reference validation

Every ID an agent cites - evidence, fact, witness, legal rule - must exist in
the authoritative case record. This module is the gate: output that references
something that does not exist is rejected, never silently accepted, and the
rejection is recorded in a form the Legal Process Auditor can consume.
"""

from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.domain import Argument, Case, ElementBinding, Verdict, utc_now

from .registry import LegalRuleRegistry


class ReferenceType(str, Enum):
    """Kinds of reference that can be validated"""

    EVIDENCE = "evidence"
    FACT = "fact"
    WITNESS = "witness"
    LAW = "law"
    CONDITION = "condition"
    ARGUMENT = "argument"


class ValidationError(BaseModel):
    """A single invalid reference"""

    reference_type: ReferenceType = Field(..., description="Kind of reference that was invalid")
    reference_id: str = Field(..., description="The offending ID as cited")
    message: str = Field(..., description="Why the reference was rejected")
    location: str = Field(default="", description="Where the reference appeared")

    def as_violation(self, agent_id: str = "", case_id: str = "") -> Dict[str, Any]:
        """Audit-report-shaped record of this violation"""
        return {
            "agent_id": agent_id,
            "case_id": case_id,
            "reference_type": self.reference_type.value,
            "reference_id": self.reference_id,
            "message": self.message,
            "location": self.location,
            "detected_at": utc_now().isoformat(),
        }


class ValidationResult(BaseModel):
    """Outcome of validating one agent output"""

    valid: bool = Field(..., description="Whether every reference resolved")
    errors: List[ValidationError] = Field(default_factory=list)
    checked_references: int = Field(default=0, description="How many references were checked")
    subject_id: str = Field(default="", description="ID of the object that was validated")

    model_config = ConfigDict(frozen=False)

    def __bool__(self) -> bool:
        return self.valid

    @property
    def messages(self) -> List[str]:
        """Error messages, suitable for a regeneration prompt"""
        return [error.message for error in self.errors]

    def as_violations(self, agent_id: str = "", case_id: str = "") -> List[Dict[str, Any]]:
        """All errors as audit-report-shaped records"""
        return [error.as_violation(agent_id, case_id) for error in self.errors]


class ReferenceValidator:
    """Validates that cited IDs exist in the case and the rule registry"""

    def __init__(self, case: Case, registry: Optional[LegalRuleRegistry] = None) -> None:
        self.case = case
        self.registry = registry or LegalRuleRegistry()
        self.evidence_ids = {item.evidence_id for item in case.evidence}
        self.fact_ids = {fact.fact_id for fact in case.facts}
        self.witness_ids = {witness.witness_id for witness in case.witnesses}

    # ------------------------------------------------------------------
    # Primitive checks
    # ------------------------------------------------------------------

    def _check(
        self,
        ids: Iterable[str],
        known: Iterable[str],
        reference_type: ReferenceType,
        location: str,
    ) -> List[ValidationError]:
        known_set = set(known)
        return [
            ValidationError(
                reference_type=reference_type,
                reference_id=reference_id,
                message=(
                    f"Unknown {reference_type.value} reference '{reference_id}' "
                    f"in {location}; it does not exist in case {self.case.case_id}."
                ),
                location=location,
            )
            for reference_id in ids
            if reference_id not in known_set
        ]

    def evidence_exists(self, evidence_id: str) -> bool:
        """Whether an evidence ID exists in the case"""
        return evidence_id in self.evidence_ids

    def fact_exists(self, fact_id: str) -> bool:
        """Whether a fact ID exists in the case"""
        return fact_id in self.fact_ids

    def witness_exists(self, witness_id: str) -> bool:
        """Whether a witness ID exists in the case"""
        return witness_id in self.witness_ids

    def law_exists(self, rule_id: str) -> bool:
        """Whether a legal rule ID exists in the registry"""
        return rule_id in self.registry

    # ------------------------------------------------------------------
    # Object-level validation
    # ------------------------------------------------------------------

    def validate_references(
        self,
        evidence_ids: Sequence[str] = (),
        fact_ids: Sequence[str] = (),
        witness_ids: Sequence[str] = (),
        law_ids: Sequence[str] = (),
        location: str = "output",
        subject_id: str = "",
    ) -> ValidationResult:
        """Validate a loose set of references"""
        errors: List[ValidationError] = []
        errors += self._check(evidence_ids, self.evidence_ids, ReferenceType.EVIDENCE, location)
        errors += self._check(fact_ids, self.fact_ids, ReferenceType.FACT, location)
        errors += self._check(witness_ids, self.witness_ids, ReferenceType.WITNESS, location)
        errors += self._check(law_ids, self.registry.rule_ids, ReferenceType.LAW, location)

        checked = len(evidence_ids) + len(fact_ids) + len(witness_ids) + len(law_ids)
        return ValidationResult(
            valid=not errors,
            errors=errors,
            checked_references=checked,
            subject_id=subject_id,
        )

    def validate_argument(
        self, argument: Argument, known_argument_ids: Sequence[str] = ()
    ) -> ValidationResult:
        """Validate every reference in an argument"""
        location = f"argument {argument.argument_id}"
        result = self.validate_references(
            evidence_ids=argument.evidence_ids,
            fact_ids=argument.fact_ids,
            witness_ids=argument.witness_ids,
            law_ids=argument.law_ids,
            location=location,
            subject_id=argument.argument_id,
        )

        counter_errors = self._check(
            argument.counter_argument_ids,
            known_argument_ids,
            ReferenceType.ARGUMENT,
            location,
        )
        result.errors.extend(counter_errors)
        result.checked_references += len(argument.counter_argument_ids)
        result.valid = not result.errors
        return result

    def validate_verdict(self, verdict: Verdict) -> ValidationResult:
        """Validate every reference in a verdict"""
        result = self.validate_references(
            evidence_ids=verdict.evidence_used,
            law_ids=verdict.laws_used,
            location=f"verdict {verdict.verdict_id}",
            subject_id=verdict.verdict_id,
        )

        if verdict.case_id != self.case.case_id:
            result.errors.append(
                ValidationError(
                    reference_type=ReferenceType.FACT,
                    reference_id=verdict.case_id,
                    message=(
                        f"Verdict {verdict.verdict_id} references case '{verdict.case_id}' "
                        f"but was validated against case '{self.case.case_id}'."
                    ),
                    location=f"verdict {verdict.verdict_id}",
                )
            )
            result.valid = False
        return result

    def validate_binding(self, binding: ElementBinding) -> ValidationResult:
        """Validate an element binding, including the rule and condition it targets"""
        location = f"binding {binding.binding_id}"
        result = self.validate_references(
            evidence_ids=binding.evidence_ids,
            fact_ids=binding.fact_ids,
            law_ids=[binding.rule_id],
            location=location,
            subject_id=binding.binding_id,
        )

        if self.law_exists(binding.rule_id):
            condition = self.registry.get_condition(binding.rule_id, binding.condition_id)
            if condition is None:
                result.errors.append(
                    ValidationError(
                        reference_type=ReferenceType.CONDITION,
                        reference_id=binding.condition_id,
                        message=(
                            f"Rule {binding.rule_id} has no condition "
                            f"'{binding.condition_id}'."
                        ),
                        location=location,
                    )
                )
            result.checked_references += 1

        if not binding.fact_ids and not binding.evidence_ids:
            result.errors.append(
                ValidationError(
                    reference_type=ReferenceType.EVIDENCE,
                    reference_id="",
                    message=(
                        f"Binding {binding.binding_id} cites neither a fact nor evidence; "
                        "a legal element cannot be bound to nothing."
                    ),
                    location=location,
                )
            )

        result.valid = not result.errors
        return result

    def validate_bindings(self, bindings: Sequence[ElementBinding]) -> ValidationResult:
        """Validate a collection of bindings, aggregating every error"""
        errors: List[ValidationError] = []
        checked = 0
        for binding in bindings:
            result = self.validate_binding(binding)
            errors.extend(result.errors)
            checked += result.checked_references

        return ValidationResult(
            valid=not errors,
            errors=errors,
            checked_references=checked,
            subject_id=self.case.case_id,
        )
