"""Validation of Judge Agent output

Three layers of checks, in decreasing severity:

1. **Reference errors** - any cited fact, evidence, rule, or argument ID that
   does not exist. Always rejected (anti-hallucination, rule E005).
2. **Structural errors** - the decision is incomplete or incoherent: a charge
   left undecided or invented, a required element not assessed, a conviction
   on an element the judge itself did not find established, or a party's
   arguments ignored entirely. Always rejected.
3. **Engine divergences** - the judge's view differs from the deterministic
   rule engine. Recorded for evaluation, not rejected by default: the engine
   weighs authored bindings with fixed thresholds, and a judge may reasonably
   disagree. With ``strict_engine_alignment`` enabled, convicting where the
   engine did not find the offense satisfied becomes a structural error.
"""

from typing import Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from app.domain import Argument, Case, FactStatus, LegalCategory
from app.rules import (
    CaseEvaluation,
    ConditionStatus,
    LegalRuleRegistry,
    ReferenceType,
    ReferenceValidator,
    RuleEvaluation,
    RuleStatus,
    ValidationError,
)

from .schema import ChargeOutcome, ElementAssessment, ElementFinding, JudgeDecisionOutput


class EngineDivergence(BaseModel):
    """A point where the judge's conclusion differs from the rule engine"""

    kind: str = Field(..., description="Category of divergence")
    charge: str = Field(default="")
    rule_id: str = Field(default="")
    condition_id: str = Field(default="")
    judge_view: str = Field(..., description="What the judge concluded")
    engine_view: str = Field(..., description="What the rule engine concluded")
    against_defendant: bool = Field(
        ..., description="True if the judge was harsher on the defendant than the engine"
    )


class JudgeValidationReport(BaseModel):
    """Outcome of validating one judge output"""

    reference_errors: List[ValidationError] = Field(default_factory=list)
    structural_errors: List[str] = Field(default_factory=list)
    divergences: List[EngineDivergence] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.reference_errors and not self.structural_errors

    @property
    def messages(self) -> List[str]:
        """All rejection reasons, suitable for a regeneration prompt"""
        return [e.message for e in self.reference_errors] + list(self.structural_errors)


class JudgeOutputValidator:
    """Checks a judge decision against the case, the rules, and the engine"""

    def __init__(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        registry: Optional[LegalRuleRegistry] = None,
        arguments: Sequence[Argument] = (),
        strict_engine_alignment: bool = False,
    ) -> None:
        self.case = case
        self.evaluation = evaluation
        self.registry = registry or LegalRuleRegistry()
        self.references = ReferenceValidator(case, self.registry)
        self.argument_ids = [a.argument_id for a in arguments]
        self.arguments_by_party: Dict[str, List[str]] = {}
        for argument in arguments:
            self.arguments_by_party.setdefault(argument.agent_id, []).append(argument.argument_id)
        self.strict_engine_alignment = strict_engine_alignment
        self._facts = {fact.fact_id: fact for fact in case.facts}

    def validate(self, output: JudgeDecisionOutput) -> JudgeValidationReport:
        report = JudgeValidationReport()
        self._check_references(output, report)
        self._check_both_sides(output, report)
        self._check_charges(output, report)
        self._check_engine_alignment(output, report)
        return report

    # ------------------------------------------------------------------
    # 1. References
    # ------------------------------------------------------------------

    def _check_references(
        self, output: JudgeDecisionOutput, report: JudgeValidationReport
    ) -> None:
        result = self.references.validate_references(
            evidence_ids=output.referenced_evidence_ids(),
            fact_ids=output.referenced_fact_ids(),
            law_ids=output.referenced_rule_ids(),
            location="judge decision",
        )
        report.reference_errors.extend(result.errors)

        for argument_id in output.arguments_considered:
            if argument_id not in self.argument_ids:
                report.reference_errors.append(
                    ValidationError(
                        reference_type=ReferenceType.ARGUMENT,
                        reference_id=argument_id,
                        message=(
                            f"Unknown argument reference '{argument_id}' in judge decision; "
                            "no such argument was presented to the court."
                        ),
                        location="judge decision",
                    )
                )

    # ------------------------------------------------------------------
    # 2. Structure
    # ------------------------------------------------------------------

    def _check_both_sides(
        self, output: JudgeDecisionOutput, report: JudgeValidationReport
    ) -> None:
        """The judge must weigh every party that presented arguments"""
        considered = set(output.arguments_considered)
        for party, argument_ids in self.arguments_by_party.items():
            if not considered.intersection(argument_ids):
                report.structural_errors.append(
                    f"No argument from {party} is listed in arguments_considered; the "
                    f"court must weigh both sides (presented: {', '.join(argument_ids)})."
                )

    def _check_charges(self, output: JudgeDecisionOutput, report: JudgeValidationReport) -> None:
        errors = report.structural_errors
        decided = [c.charge for c in output.charge_decisions]

        for charge in self.case.charges:
            count = decided.count(charge)
            if count == 0:
                errors.append(f"Charge '{charge}' was not decided; every charge needs a decision.")
            elif count > 1:
                errors.append(f"Charge '{charge}' was decided {count} times; decide it once.")

        for charge in sorted(set(decided) - set(self.case.charges)):
            errors.append(
                f"Charge '{charge}' is not one of the charges in this case "
                f"({', '.join(self.case.charges)}); do not invent charges."
            )

        for decision in output.charge_decisions:
            rule = self.registry.get(decision.rule_id)
            if rule is None:
                continue  # already reported as a reference error

            if rule.category != LegalCategory.OFFENSE:
                errors.append(
                    f"Charge '{decision.charge}' is decided under {rule.rule_id} "
                    f"({rule.name}), which is not an offense."
                )
                continue

            for defense_id in decision.defenses_considered:
                defense = self.registry.get(defense_id)
                if defense is not None and defense.category != LegalCategory.DEFENSE:
                    errors.append(
                        f"{defense_id} ({defense.name}) is listed as a defense for "
                        f"'{decision.charge}' but is not a defense rule."
                    )

            known = {c.id for c in rule.conditions}
            assessed = [e.condition_id for e in decision.elements]
            for condition_id in assessed:
                if condition_id not in known:
                    errors.append(
                        f"{rule.rule_id} has no condition '{condition_id}' "
                        f"(conditions: {', '.join(sorted(known))})."
                    )

            required = [c.id for c in rule.conditions if c.required]
            missing = [c for c in required if c not in assessed]
            if missing:
                errors.append(
                    f"Charge '{decision.charge}' does not assess required element(s) "
                    f"{', '.join(missing)} of {rule.rule_id}; every element must be addressed."
                )

            if decision.decision == ChargeOutcome.GUILTY:
                unproven = [
                    e.condition_id
                    for e in decision.elements
                    if e.condition_id in required
                    and e.assessment != ElementAssessment.ESTABLISHED
                ]
                if unproven:
                    errors.append(
                        f"Charge '{decision.charge}' is decided guilty although element(s) "
                        f"{', '.join(unproven)} were not found established (P002, P004)."
                    )

    # ------------------------------------------------------------------
    # 3. Engine alignment
    # ------------------------------------------------------------------

    def _check_engine_alignment(
        self, output: JudgeDecisionOutput, report: JudgeValidationReport
    ) -> None:
        defendant = self.case.defendant

        for finding in output.established_facts:
            fact = self._facts.get(finding.fact_id)
            if fact is not None and fact.status == FactStatus.DISPUTED:
                report.divergences.append(
                    EngineDivergence(
                        kind="disputed_fact_treated_as_established",
                        judge_view=f"{fact.fact_id} established",
                        engine_view=f"{fact.fact_id} recorded as disputed",
                        against_defendant=True,
                    )
                )

        for decision in output.charge_decisions:
            engine_rule = self._engine_rule(decision.rule_id, defendant)
            if engine_rule is None:
                continue

            engine_conditions: Dict[str, ConditionStatus] = {
                c.condition_id: c.status for c in engine_rule.conditions
            }
            for element in decision.elements:
                engine_status = engine_conditions.get(element.condition_id)
                if engine_status is None:
                    continue
                if element.assessment == ElementAssessment.ESTABLISHED and engine_status in (
                    ConditionStatus.UNSATISFIED,
                    ConditionStatus.UNSUPPORTED,
                ):
                    report.divergences.append(
                        self._element_divergence(
                            decision.charge, decision.rule_id, element, engine_status, True
                        )
                    )
                elif (
                    element.assessment == ElementAssessment.NOT_ESTABLISHED
                    and engine_status == ConditionStatus.SATISFIED
                ):
                    report.divergences.append(
                        self._element_divergence(
                            decision.charge, decision.rule_id, element, engine_status, False
                        )
                    )

            engine_satisfied = engine_rule.status == RuleStatus.SATISFIED
            if decision.decision == ChargeOutcome.GUILTY and not engine_satisfied:
                report.divergences.append(
                    EngineDivergence(
                        kind="conviction_without_engine_support",
                        charge=decision.charge,
                        rule_id=decision.rule_id,
                        judge_view="guilty",
                        engine_view=f"{decision.rule_id} {engine_rule.status.value}",
                        against_defendant=True,
                    )
                )
                if self.strict_engine_alignment:
                    report.structural_errors.append(
                        f"Charge '{decision.charge}' is decided guilty, but the rule engine "
                        f"evaluates {decision.rule_id} as '{engine_rule.status.value}' for "
                        f"{defendant}. Strict alignment requires the engine to find every "
                        "element satisfied before a conviction."
                    )
            elif decision.decision == ChargeOutcome.NOT_GUILTY and engine_satisfied:
                report.divergences.append(
                    EngineDivergence(
                        kind="acquittal_despite_engine_support",
                        charge=decision.charge,
                        rule_id=decision.rule_id,
                        judge_view="not_guilty",
                        engine_view=f"{decision.rule_id} satisfied",
                        against_defendant=False,
                    )
                )

    def _engine_rule(self, rule_id: str, subject: str) -> Optional[RuleEvaluation]:
        matches = self.evaluation.for_rule(rule_id, subject)
        return matches[0] if matches else None

    @staticmethod
    def _element_divergence(
        charge: str,
        rule_id: str,
        element: ElementFinding,
        engine_status: ConditionStatus,
        against_defendant: bool,
    ) -> EngineDivergence:
        return EngineDivergence(
            kind="element_assessment",
            charge=charge,
            rule_id=rule_id,
            condition_id=element.condition_id,
            judge_view=element.assessment.value,
            engine_view=engine_status.value,
            against_defendant=against_defendant,
        )
