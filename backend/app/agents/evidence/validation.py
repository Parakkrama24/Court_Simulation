"""Validation of Evidence Agent output

Rejected (the agent must regenerate):

- **References** - any fact, evidence, witness, argument, or legal element
  that is not in the record.
- **Status consistency** - a claim's status must agree with its own
  citations: ``established`` needs support and no contradiction, ``disputed``
  needs both, ``unsupported`` has no support. An item cannot both support and
  contradict the same claim.
- **Completeness** - every evidence item and every witness is assessed exactly
  once; every fact the record marks as disputed is covered by at least one
  claim (P005); every contradiction names at least two items; a review covers
  every argument once and explains any finding short of ``supported``.

Recorded, not rejected (flags):

- **Neutrality** - language about guilt, conviction, or acquittal. The agent
  analyses evidence; it does not decide the case. A keyword heuristic, so it
  flags rather than rejects.
- **Engine divergence** - rating a witness in a different band from the
  deterministic E003 score, calling ``circumstantial``-type evidence direct,
  or leaving a fact conflict the engine found out of the contradictions.
"""

import re
from typing import Dict, Iterable, List, Sequence

from pydantic import BaseModel, Field

from app.domain import Argument, Case, EvidenceType, FactStatus
from app.rules import CaseEvaluation, LegalRuleRegistry, ReferenceValidator

from .schema import (
    ArgumentSupport,
    ClaimStatus,
    Directness,
    EvidenceAnalysisOutput,
    EvidenceReviewOutput,
    ReliabilityRating,
)

MAX_CLAIMS = 20

_NEUTRALITY_PATTERN = re.compile(r"\b(guilty|guilt|convict\w*|acquit\w*|innocent)\b", re.I)


def reliability_band(score: float) -> ReliabilityRating:
    """Map a deterministic E003 score onto a rating band"""
    if score >= 0.75:
        return ReliabilityRating.HIGH
    if score >= 0.4:
        return ReliabilityRating.MODERATE
    return ReliabilityRating.LOW


class EvidenceFlag(BaseModel):
    """A concern about accepted output, recorded for later audit"""

    kind: str
    detail: str


class EvidenceValidationReport(BaseModel):
    """Outcome of validating one Evidence Agent output"""

    errors: List[str] = Field(default_factory=list)
    flags: List[EvidenceFlag] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def _neutrality_flags(texts: Iterable[str]) -> List[EvidenceFlag]:
    hits = sorted({m.group(0).lower() for t in texts for m in _NEUTRALITY_PATTERN.finditer(t)})
    if not hits:
        return []
    return [
        EvidenceFlag(
            kind="neutrality",
            detail=f"Uses outcome language ({', '.join(hits)}); the Evidence Agent is neutral.",
        )
    ]


def _count_errors(label: str, expected: Sequence[str], seen: Sequence[str]) -> List[str]:
    errors = []
    for item_id in expected:
        count = seen.count(item_id)
        if count == 0:
            errors.append(f"{label} {item_id} is not assessed; assess every {label} once.")
        elif count > 1:
            errors.append(f"{label} {item_id} is assessed {count} times; assess it once.")
    return errors


class EvidenceAnalysisValidator:
    """Checks an EVIDENCE_ANALYSIS output against the record"""

    def __init__(
        self,
        case: Case,
        evaluation: CaseEvaluation,
        registry: LegalRuleRegistry | None = None,
    ) -> None:
        self.case = case
        self.evaluation = evaluation
        self.registry = registry or LegalRuleRegistry()
        self.references = ReferenceValidator(case, self.registry)

    def validate(self, output: EvidenceAnalysisOutput) -> EvidenceValidationReport:
        report = EvidenceValidationReport()
        self._check_references(output, report)
        self._check_claims(output, report)
        self._check_completeness(output, report)
        self._check_contradictions(output, report)
        report.flags += _neutrality_flags(
            [output.summary]
            + [c.claim + " " + c.reasoning for c in output.claims]
            + [e.reasoning for e in output.evidence]
            + [w.reasoning for w in output.witnesses]
        )
        self._check_engine_alignment(output, report)
        return report

    def _check_references(
        self, output: EvidenceAnalysisOutput, report: EvidenceValidationReport
    ) -> None:
        evidence_ids: List[str] = []
        witness_ids: List[str] = []
        fact_ids: List[str] = []
        rule_ids: List[str] = []
        for claim in output.claims:
            fact_ids += claim.fact_ids
            evidence_ids += claim.supporting_evidence_ids + claim.contradicting_evidence_ids
            witness_ids += claim.supporting_witness_ids + claim.contradicting_witness_ids
        for item in output.evidence:
            evidence_ids.append(item.evidence_id)
            fact_ids += item.fact_ids
        for contradiction in output.contradictions:
            evidence_ids += contradiction.evidence_ids
            witness_ids += contradiction.witness_ids
            fact_ids += contradiction.fact_ids
        witness_ids += [w.witness_id for w in output.witnesses]
        for missing in output.missing_evidence:
            rule_ids += [e.rule_id for e in missing.elements]

        result = self.references.validate_references(
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            fact_ids=list(dict.fromkeys(fact_ids)),
            witness_ids=list(dict.fromkeys(witness_ids)),
            law_ids=list(dict.fromkeys(rule_ids)),
            location="evidence analysis",
        )
        report.errors += result.messages

        for missing in output.missing_evidence:
            for element in missing.elements:
                if element.rule_id in self.registry and self.registry.get_condition(
                    element.rule_id, element.condition_id
                ) is None:
                    report.errors.append(
                        f"missing evidence: {element.rule_id} has no condition "
                        f"'{element.condition_id}'."
                    )

    def _check_claims(
        self, output: EvidenceAnalysisOutput, report: EvidenceValidationReport
    ) -> None:
        if not output.claims:
            report.errors.append("No claims were assessed; assess the important claims.")
        if len(output.claims) > MAX_CLAIMS:
            report.errors.append(
                f"{len(output.claims)} claims were assessed; keep to the {MAX_CLAIMS} most "
                "important."
            )

        for index, claim in enumerate(output.claims, start=1):
            where = f"claim {index} ({claim.claim[:60]!r})"
            support = claim.supporting_evidence_ids + claim.supporting_witness_ids
            contra = claim.contradicting_evidence_ids + claim.contradicting_witness_ids

            both = sorted(set(support) & set(contra))
            if both:
                report.errors.append(
                    f"{where}: {', '.join(both)} cannot both support and contradict the claim."
                )

            if claim.status == ClaimStatus.ESTABLISHED and (not support or contra):
                report.errors.append(
                    f"{where}: 'established' requires supporting evidence and no "
                    "contradicting evidence; a contradicted claim is 'disputed'."
                )
            elif claim.status == ClaimStatus.DISPUTED and not (support and contra):
                report.errors.append(
                    f"{where}: 'disputed' requires both supporting and contradicting evidence."
                )
            elif claim.status == ClaimStatus.UNSUPPORTED and support:
                report.errors.append(
                    f"{where}: 'unsupported' cannot list supporting evidence; if something "
                    "supports it, it is 'established' or 'disputed'."
                )

    def _check_completeness(
        self, output: EvidenceAnalysisOutput, report: EvidenceValidationReport
    ) -> None:
        report.errors += _count_errors(
            "evidence",
            [e.evidence_id for e in self.case.evidence],
            [e.evidence_id for e in output.evidence],
        )
        report.errors += _count_errors(
            "witness",
            [w.witness_id for w in self.case.witnesses],
            [w.witness_id for w in output.witnesses],
        )

        covered = {fid for claim in output.claims for fid in claim.fact_ids}
        for fact in self.case.facts:
            if fact.status == FactStatus.DISPUTED and fact.fact_id not in covered:
                report.errors.append(
                    f"Disputed fact {fact.fact_id} ({fact.description}) is not covered by any "
                    "claim; contradictory evidence must be addressed (P005)."
                )

    def _check_contradictions(
        self, output: EvidenceAnalysisOutput, report: EvidenceValidationReport
    ) -> None:
        for index, contradiction in enumerate(output.contradictions, start=1):
            items = (
                len(contradiction.evidence_ids)
                + len(contradiction.witness_ids)
                + len(contradiction.fact_ids)
            )
            if items < 2:
                report.errors.append(
                    f"contradiction {index}: name at least two items that conflict."
                )

    def _check_engine_alignment(
        self, output: EvidenceAnalysisOutput, report: EvidenceValidationReport
    ) -> None:
        scores = {w.witness_id: w.reliability_score for w in self.evaluation.witness_assessments}
        for witness in output.witnesses:
            score = scores.get(witness.witness_id)
            if score is None:
                continue
            band = reliability_band(score)
            if witness.rating != band:
                report.flags.append(
                    EvidenceFlag(
                        kind="witness_rating_divergence",
                        detail=(
                            f"{witness.witness_id} rated {witness.rating.value}; the E003 "
                            f"score {score:.2f} falls in the {band.value} band."
                        ),
                    )
                )

        types: Dict[str, EvidenceType] = {e.evidence_id: e.type for e in self.case.evidence}
        for item in output.evidence:
            if (
                types.get(item.evidence_id) == EvidenceType.CIRCUMSTANTIAL
                and item.directness == Directness.DIRECT
            ):
                report.flags.append(
                    EvidenceFlag(
                        kind="directness_divergence",
                        detail=(
                            f"{item.evidence_id} is recorded as circumstantial evidence but "
                            "was assessed as direct."
                        ),
                    )
                )

        named = {fid for c in output.contradictions for fid in c.fact_ids}
        for conflict in self.evaluation.conflicting_evidence:
            fact_id = conflict.get("fact_id")
            if conflict.get("type") != "condition_conflict" and fact_id and fact_id not in named:
                report.flags.append(
                    EvidenceFlag(
                        kind="engine_conflict_not_named",
                        detail=f"The rule engine found a conflict on {fact_id} (E004) that "
                        "no contradiction names.",
                    )
                )


class EvidenceReviewValidator:
    """Checks an EVIDENCE_REVIEW output against the arguments under review"""

    def __init__(self, arguments: Sequence[Argument]) -> None:
        self.argument_ids = [a.argument_id for a in arguments]

    def validate(self, output: EvidenceReviewOutput) -> EvidenceValidationReport:
        report = EvidenceValidationReport()
        reviewed = [r.argument_id for r in output.reviews]

        for argument_id in sorted(set(reviewed) - set(self.argument_ids)):
            report.errors.append(
                f"Argument '{argument_id}' is not under review; review only the listed arguments."
            )
        report.errors += _count_errors("argument", self.argument_ids, reviewed)

        for review in output.reviews:
            if review.support != ArgumentSupport.SUPPORTED and not review.issues:
                report.errors.append(
                    f"{review.argument_id} is '{review.support.value}' but lists no issues; "
                    "say what the citations fail to support."
                )

        report.flags += _neutrality_flags(
            [output.summary] + [r.reasoning for r in output.reviews]
        )
        return report
