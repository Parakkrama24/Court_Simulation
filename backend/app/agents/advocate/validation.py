"""Validation of Prosecution and Defense turns

Rejected (the advocate must regenerate):

- **References**: any fact, evidence, witness, or rule ID not in the record,
  or a legal element (rule + condition) that does not exist. Advocates cannot
  invent facts, evidence, witnesses, or laws.
- **Grounding**: an argument that cites no fact, evidence, or witness at all
  (P003 - a claim is not a fact because an agent states it).
- **Scope**: a charge that is not in the case; an empty turn or one with more
  than ``MAX_ARGUMENTS_PER_TURN`` arguments.
- **Debate references**: ``responds_to`` naming an argument that was never
  presented, the advocate's own side's argument, or a question put to the
  other party; a rebuttal argument that answers nothing.
- **Cross-examination**: an argument that tests no witness's testimony.
- **Answering the judge**: a question put to this party left unanswered.

Recorded, not rejected (flags for the auditor):

- an argument that relies on a fact the record marks as disputed without
  listing any assumption.
"""

from typing import Dict, List, Sequence

from pydantic import BaseModel, Field

from app.domain import Argument, Case, CourtStage, FactStatus, JudgeQuestion
from app.rules import LegalRuleRegistry, ReferenceValidator

from .roles import ANSWER_STAGE, REBUTTAL_STAGES, AdvocateRole
from .schema import AdvocateTurnOutput

MAX_ARGUMENTS_PER_TURN = 8


class AdvocacyFlag(BaseModel):
    """A weakness in an accepted argument, recorded for later audit"""

    argument_index: int = Field(..., description="Position of the argument in the turn (1-based)")
    kind: str
    detail: str


class AdvocateValidationReport(BaseModel):
    """Outcome of validating one advocate turn"""

    errors: List[str] = Field(default_factory=list)
    flags: List[AdvocacyFlag] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


class AdvocateTurnValidator:
    """Checks one advocate turn against the record and the debate so far"""

    def __init__(
        self,
        case: Case,
        role: AdvocateRole,
        stage: CourtStage,
        prior_arguments: Sequence[Argument] = (),
        registry: LegalRuleRegistry | None = None,
        questions: Sequence[JudgeQuestion] = (),
    ) -> None:
        self.case = case
        self.role = role
        self.stage = stage
        self.registry = registry or LegalRuleRegistry()
        self.references = ReferenceValidator(case, self.registry)
        self._party_of: Dict[str, str] = {a.argument_id: a.agent_id for a in prior_arguments}
        self._facts = {fact.fact_id: fact for fact in case.facts}
        self._questions = {q.question_id: q for q in questions}
        self._own_questions = [
            q.question_id for q in questions if q.addressed_to == role.agent_id
        ]

    def validate(self, output: AdvocateTurnOutput) -> AdvocateValidationReport:
        report = AdvocateValidationReport()
        errors = report.errors

        if not output.arguments:
            errors.append("The turn contains no arguments; present at least one.")
        if len(output.arguments) > MAX_ARGUMENTS_PER_TURN:
            errors.append(
                f"The turn contains {len(output.arguments)} arguments; present at most "
                f"{MAX_ARGUMENTS_PER_TURN} of your strongest."
            )

        for index, draft in enumerate(output.arguments, start=1):
            where = f"argument {index}"

            element_rules = [e.rule_id for e in draft.elements]
            refs = self.references.validate_references(
                evidence_ids=draft.evidence_ids,
                fact_ids=draft.fact_ids,
                witness_ids=draft.witness_ids,
                law_ids=list(dict.fromkeys(draft.law_ids + element_rules)),
                location=where,
            )
            errors.extend(refs.messages)

            for element in draft.elements:
                if element.rule_id in self.registry and self.registry.get_condition(
                    element.rule_id, element.condition_id
                ) is None:
                    errors.append(
                        f"{where}: {element.rule_id} has no condition '{element.condition_id}'."
                    )

            if not draft.charges:
                errors.append(f"{where}: name the charge(s) the argument concerns.")
            for charge in draft.charges:
                if charge not in self.case.charges:
                    errors.append(
                        f"{where}: '{charge}' is not a charge in this case "
                        f"({', '.join(self.case.charges)})."
                    )

            if not (draft.fact_ids or draft.evidence_ids or draft.witness_ids):
                errors.append(
                    f"{where}: cites no fact, evidence, or witness; every claim must be "
                    "grounded in the record (P003)."
                )

            for argument_id in draft.responds_to:
                question = self._questions.get(argument_id)
                if question is not None:
                    if question.addressed_to != self.role.agent_id:
                        errors.append(
                            f"{where}: responds_to names question '{argument_id}', which the "
                            "judge put to the other party."
                        )
                    continue
                party = self._party_of.get(argument_id)
                if party is None:
                    errors.append(
                        f"{where}: responds_to names '{argument_id}', which has not been "
                        "presented in this trial."
                    )
                elif party == self.role.agent_id:
                    errors.append(
                        f"{where}: responds_to names '{argument_id}', your own side's "
                        "argument; responds_to may only name the opposing party's arguments."
                    )

            if self.stage == CourtStage.CROSS_EXAMINATION and not draft.witness_ids:
                errors.append(
                    f"{where}: this is cross-examination; every argument must test the "
                    "testimony of at least one witness (witness_ids), on the E003 grounds."
                )

            if self.stage in REBUTTAL_STAGES and not draft.responds_to:
                errors.append(
                    f"{where}: this is a rebuttal; every argument must answer at least one "
                    "opposing argument by ID in responds_to."
                )

            disputed = [
                fid
                for fid in draft.fact_ids
                if fid in self._facts and self._facts[fid].status == FactStatus.DISPUTED
            ]
            if disputed and not draft.assumptions:
                report.flags.append(
                    AdvocacyFlag(
                        argument_index=index,
                        kind="disputed_fact_without_assumption",
                        detail=(
                            f"Relies on disputed fact(s) {', '.join(disputed)} without "
                            "listing any assumption."
                        ),
                    )
                )

        if self.stage == ANSWER_STAGE:
            answered = {rid for draft in output.arguments for rid in draft.responds_to}
            for question_id in self._own_questions:
                if question_id not in answered:
                    errors.append(
                        f"The judge's question {question_id} is not answered; put its ID in "
                        "responds_to of the argument that answers it."
                    )

        return report
