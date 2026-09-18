"""The verdict engine: deterministic tallying of jury votes

The architecture places a Verdict Engine between the jurors and the judge.
Counting votes is not a judgement call, so it is code: given each juror's
verdict per charge and a decision rule, it returns the jury's verdict per
charge, whether the panel was unanimous, how often jurors agreed, and which
votes changed in deliberation - the "verdict agreement" metric of spec
section 23.
"""

from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence

from pydantic import BaseModel, Field

from ..judge.schema import ChargeOutcome
from .schema import JurorVerdictOutput


class JuryRule(str, Enum):
    """How votes become a verdict"""

    UNANIMOUS = "unanimous"  # any split is a hung jury
    MAJORITY = "majority"  # more than half; a tie is a hung jury


class JuryOutcome(str, Enum):
    """The jury's verdict on one charge"""

    GUILTY = "guilty"
    NOT_GUILTY = "not_guilty"
    HUNG = "hung"


class ChargeTally(BaseModel):
    """Votes on one charge"""

    charge: str
    guilty: List[str] = Field(default_factory=list, description="Jurors voting guilty")
    not_guilty: List[str] = Field(default_factory=list, description="Jurors voting not guilty")
    outcome: JuryOutcome
    unanimous: bool
    agreement: float = Field(
        ..., ge=0.0, le=1.0, description="Share of jurors on the larger side"
    )


class VoteChange(BaseModel):
    """A juror who changed their vote on a charge during deliberation"""

    juror_id: str
    charge: str
    before: ChargeOutcome
    after: ChargeOutcome


class JuryResult(BaseModel):
    """The panel's verdict, before and after deliberation"""

    rule: JuryRule
    jurors: List[str]
    independent: List[ChargeTally]
    final: List[ChargeTally]
    vote_changes: List[VoteChange] = Field(default_factory=list)
    deliberated: bool = False

    @property
    def independent_agreement(self) -> float:
        """Mean agreement across charges before deliberation"""
        return _mean([t.agreement for t in self.independent])

    @property
    def final_agreement(self) -> float:
        """Mean agreement across charges after deliberation"""
        return _mean([t.agreement for t in self.final])

    def outcome(self, charge: str) -> Optional[JuryOutcome]:
        for tally in self.final:
            if tally.charge == charge:
                return tally.outcome
        return None


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def tally_votes(
    decisions: Mapping[str, JurorVerdictOutput],
    charges: Sequence[str],
    rule: JuryRule = JuryRule.UNANIMOUS,
) -> List[ChargeTally]:
    """Count one round of votes, charge by charge"""
    if not decisions:
        raise ValueError("A jury needs at least one juror")

    size = len(decisions)
    tallies = []
    for charge in charges:
        guilty: List[str] = []
        not_guilty: List[str] = []
        for juror_id, output in decisions.items():
            vote = _vote(output, charge)
            (guilty if vote == ChargeOutcome.GUILTY else not_guilty).append(juror_id)

        if rule == JuryRule.UNANIMOUS:
            if len(guilty) == size:
                outcome = JuryOutcome.GUILTY
            elif len(not_guilty) == size:
                outcome = JuryOutcome.NOT_GUILTY
            else:
                outcome = JuryOutcome.HUNG
        else:
            if len(guilty) * 2 > size:
                outcome = JuryOutcome.GUILTY
            elif len(not_guilty) * 2 > size:
                outcome = JuryOutcome.NOT_GUILTY
            else:
                outcome = JuryOutcome.HUNG

        tallies.append(
            ChargeTally(
                charge=charge,
                guilty=guilty,
                not_guilty=not_guilty,
                outcome=outcome,
                unanimous=len(guilty) == size or len(not_guilty) == size,
                agreement=round(max(len(guilty), len(not_guilty)) / size, 4),
            )
        )
    return tallies


def _vote(output: JurorVerdictOutput, charge: str) -> ChargeOutcome:
    for verdict in output.charge_verdicts:
        if verdict.charge == charge:
            return verdict.verdict
    # Validation guarantees every charge is decided; fail loudly if not.
    raise ValueError(f"No verdict on charge '{charge}'")


def aggregate_jury(
    independent: Mapping[str, JurorVerdictOutput],
    charges: Sequence[str],
    rule: JuryRule = JuryRule.UNANIMOUS,
    deliberation: Optional[Mapping[str, JurorVerdictOutput]] = None,
) -> JuryResult:
    """Tally the independent round and, if held, the deliberation round"""
    before = tally_votes(independent, charges, rule)
    after = tally_votes(deliberation, charges, rule) if deliberation else before

    changes: List[VoteChange] = []
    if deliberation:
        for juror_id, output in deliberation.items():
            for charge in charges:
                old, new = _vote(independent[juror_id], charge), _vote(output, charge)
                if old != new:
                    changes.append(
                        VoteChange(juror_id=juror_id, charge=charge, before=old, after=new)
                    )

    return JuryResult(
        rule=rule,
        jurors=list(independent.keys()),
        independent=before,
        final=after,
        vote_changes=changes,
        deliberated=deliberation is not None,
    )


def judge_jury_agreement(
    judge_decisions: Mapping[str, ChargeOutcome], jury: JuryResult
) -> List[Dict[str, object]]:
    """Per charge: does the judge's decision match the jury's final verdict?"""
    rows: List[Dict[str, object]] = []
    for tally in jury.final:
        judge = judge_decisions.get(tally.charge)
        rows.append(
            {
                "charge": tally.charge,
                "judge": judge.value if judge else None,
                "jury": tally.outcome.value,
                "agrees": judge is not None and judge.value == tally.outcome.value,
            }
        )
    return rows


def jury_context(result: JuryResult) -> Dict[str, object]:
    """The jury's result as plain data for the shared case record"""
    return {
        "rule": result.rule.value,
        "deliberated": result.deliberated,
        "verdicts": [
            {
                "charge": t.charge,
                "outcome": t.outcome.value,
                "guilty_votes": len(t.guilty),
                "not_guilty_votes": len(t.not_guilty),
                "unanimous": t.unanimous,
            }
            for t in result.final
        ],
        "vote_changes_in_deliberation": len(result.vote_changes),
    }

