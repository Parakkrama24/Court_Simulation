"""Validation of juror output

Rejected (the juror must regenerate):

- **References** - any fact, evidence, witness, rule, or argument ID not in
  the record or not presented at trial.
- **Charges** - every charge decided exactly once, none invented.
- **Law** - each charge verdict relies on at least one offense rule; a charge
  cannot be decided without the law it is decided under.
- **Grounding** - a guilty verdict cites at least one fact, evidence item, or
  witness (P003). A not-guilty verdict may rest on the absence of proof (P002).
- **Both sides** - with arguments on the record, at least one from each party
  is listed as considered.
- **Deliberation** - a juror who changes a verdict must ground the new verdict
  in the record (at least one fact, evidence item, or witness). Changing a
  vote because others voted differently is not enough.
"""

from typing import Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from app.domain import Argument, Case, LegalCategory
from app.rules import LegalRuleRegistry, ReferenceValidator

from ..judge.schema import ChargeOutcome
from .schema import JurorVerdictOutput


class JurorValidationReport(BaseModel):
    """Outcome of validating one juror output"""

    errors: List[str] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


class JurorOutputValidator:
    """Checks one juror's decision against the record and the trial"""

    def __init__(
        self,
        case: Case,
        arguments: Sequence[Argument] = (),
        registry: Optional[LegalRuleRegistry] = None,
        previous: Optional[JurorVerdictOutput] = None,
    ) -> None:
        self.case = case
        self.registry = registry or LegalRuleRegistry()
        self.references = ReferenceValidator(case, self.registry)
        self.argument_ids = [a.argument_id for a in arguments]
        self.by_party: Dict[str, List[str]] = {}
        for argument in arguments:
            self.by_party.setdefault(argument.agent_id, []).append(argument.argument_id)
        self.previous = previous

    def validate(self, output: JurorVerdictOutput) -> JurorValidationReport:
        report = JurorValidationReport()
        errors = report.errors

        # References
        facts: List[str] = []
        evidence: List[str] = []
        witnesses: List[str] = []
        rules: List[str] = []
        for verdict in output.charge_verdicts:
            facts += verdict.fact_ids
            evidence += verdict.evidence_ids
            witnesses += verdict.witness_ids
            rules += verdict.rule_ids
        errors += self.references.validate_references(
            evidence_ids=list(dict.fromkeys(evidence)),
            fact_ids=list(dict.fromkeys(facts)),
            witness_ids=list(dict.fromkeys(witnesses)),
            law_ids=list(dict.fromkeys(rules)),
            location="juror verdict",
        ).messages
        for argument_id in output.arguments_considered:
            if argument_id not in self.argument_ids:
                errors.append(
                    f"Unknown argument reference '{argument_id}'; no such argument was "
                    "presented at trial."
                )

        # Charges
        decided = [v.charge for v in output.charge_verdicts]
        for charge in self.case.charges:
            count = decided.count(charge)
            if count == 0:
                errors.append(f"Charge '{charge}' has no verdict; decide every charge.")
            elif count > 1:
                errors.append(f"Charge '{charge}' has {count} verdicts; give one.")
        for charge in sorted(set(decided) - set(self.case.charges)):
            errors.append(
                f"'{charge}' is not a charge in this case ({', '.join(self.case.charges)})."
            )

        # Law and grounding, per charge
        for verdict in output.charge_verdicts:
            offenses = [
                rid
                for rid in verdict.rule_ids
                if (rule := self.registry.get(rid)) is not None
                and rule.category == LegalCategory.OFFENSE
            ]
            if not offenses:
                errors.append(
                    f"The verdict on '{verdict.charge}' relies on no offense rule; name the "
                    "offense the charge is decided under."
                )
            grounded = verdict.fact_ids or verdict.evidence_ids or verdict.witness_ids
            if verdict.verdict == ChargeOutcome.GUILTY and not grounded:
                errors.append(
                    f"The guilty verdict on '{verdict.charge}' cites no fact, evidence, or "
                    "witness; a conviction must rest on the record (P003)."
                )

        # Both sides
        considered = set(output.arguments_considered)
        for party, ids in self.by_party.items():
            if not considered.intersection(ids):
                errors.append(
                    f"No argument from {party} is listed in arguments_considered; weigh both "
                    "sides."
                )

        # Deliberation: a changed vote must be grounded in the record
        if self.previous is not None:
            before = {v.charge: v.verdict for v in self.previous.charge_verdicts}
            for verdict in output.charge_verdicts:
                changed = verdict.charge in before and before[verdict.charge] != verdict.verdict
                grounded = verdict.fact_ids or verdict.evidence_ids or verdict.witness_ids
                if changed and not grounded:
                    errors.append(
                        f"You changed your verdict on '{verdict.charge}' without citing the "
                        "record; a changed verdict must rest on facts or evidence, not on how "
                        "others voted."
                    )

        return report
