"""Prompt construction for jury agents

The independent-round prompt is built from the record alone - it has no
input through which another juror's decision could reach it. Only the
deliberation prompt adds the panel's independent verdicts. Bump
``PROMPT_VERSION`` whenever the wording changes.
"""

import json
from typing import Any, Dict, List, Optional, Sequence

from app.domain import Argument, Case
from app.rules import CaseEvaluation, LegalRuleRegistry

from ..record import render_case_record
from .schema import JurorVerdictOutput

PROMPT_VERSION = "juror.v1"

_SYSTEM = """\
You are {juror_id}, a member of the jury in a court simulation set in the Republic of \
Arandia, a fictional jurisdiction. This is a research simulation: it does not provide \
legal advice and does not determine anyone's real legal rights or obligations.

## Your task

Decide each charge - guilty or not guilty - on the record alone. You have heard the \
whole trial: the record contains the facts, evidence, witnesses, the legal rules of \
Arandia, a deterministic rule-engine evaluation, the parties' arguments, and, when \
present, the court's neutral evidence analysis.

Apply these principles:
- P001 The defendant is presumed innocent.
- P002 The prosecution must prove every required element of an offense.
- P003 A statement is not a fact because someone asserts it.
- P004 If substantial doubt remains on any required element, the verdict on that charge \
is not guilty.
- P005 Contradictory evidence must be weighed, not ignored.

Arguments are advocacy, not evidence: weigh both sides, and count a claim only as far as \
the facts and evidence it cites support it.

## What to give

For each charge: your verdict; the facts, evidence, and witnesses you relied on; the \
legal rules you relied on, including the offense the charge is decided under; a concise \
rationale; and your confidence from 0.0 to 1.0. A guilty verdict must cite what in the \
record proves it. List the arguments you weighed (at least one from each party that \
argued), what you remain uncertain about, and your overall reasoning.

Cite only IDs that appear in the record; a validation layer checks every ID, and output \
that cites anything else is rejected. Write reasoning as concise rationales a reader \
can check against the record - not a transcript of your deliberation.

Respond with a single JSON object matching the required schema."""


def build_system_prompt(juror_id: str, perspective: Optional[str] = None) -> str:
    """System prompt for one juror, with an optional research perspective"""
    prompt = _SYSTEM.format(juror_id=juror_id)
    if perspective:
        prompt += f"\n\n## Your background\n\n{perspective}"
    return prompt


def _record_block(
    case: Case,
    evaluation: CaseEvaluation,
    registry: LegalRuleRegistry,
    arguments: Sequence[Argument],
    evidence_context: Optional[Dict[str, Any]],
) -> str:
    record = render_case_record(case, evaluation, registry, arguments, evidence_context)
    return "<case_record>\n" + json.dumps(record, indent=2) + "\n</case_record>\n\n"


def build_independent_prompt(
    case: Case,
    evaluation: CaseEvaluation,
    registry: LegalRuleRegistry,
    arguments: Sequence[Argument] = (),
    evidence_context: Optional[Dict[str, Any]] = None,
) -> str:
    """JURY_INDEPENDENT_DELIBERATION: the record, and nothing from other jurors"""
    return _record_block(case, evaluation, registry, arguments, evidence_context) + (
        f"Stage: JURY_INDEPENDENT_DELIBERATION. Decide each charge against "
        f"{case.defendant} ({', '.join(case.charges)}) on your own. You have not seen, "
        "and will not see before deciding, any other juror's view."
    )


def build_deliberation_prompt(
    case: Case,
    evaluation: CaseEvaluation,
    registry: LegalRuleRegistry,
    arguments: Sequence[Argument],
    evidence_context: Optional[Dict[str, Any]],
    juror_id: str,
    panel: Dict[str, JurorVerdictOutput],
) -> str:
    """JURY_DELIBERATION: the record plus every juror's independent decision"""
    room = {
        other_id: {
            "you": other_id == juror_id,
            "charge_verdicts": [
                {
                    "charge": v.charge,
                    "verdict": v.verdict.value,
                    "fact_ids": v.fact_ids,
                    "evidence_ids": v.evidence_ids,
                    "witness_ids": v.witness_ids,
                    "rule_ids": v.rule_ids,
                    "reasoning": v.reasoning,
                    "confidence": v.confidence,
                }
                for v in decision.charge_verdicts
            ],
            "uncertainties": decision.uncertainties,
            "reasoning": decision.reasoning,
        }
        for other_id, decision in panel.items()
    }
    return (
        _record_block(case, evaluation, registry, arguments, evidence_context)
        + "<jury_room>\n"
        + json.dumps(room, indent=2)
        + "\n</jury_room>\n\n"
        + f"Stage: JURY_DELIBERATION. Above are the independent decisions of every "
        f"juror; yours is marked \"you\": true. Consider the others' reasoning against "
        "the record and give your final verdict on each charge. Change a verdict only "
        "if the record persuades you - not because of how many jurors voted which way - "
        "and when you change one, cite what in the record changed your mind. In "
        "response_to_panel, say which of the others' points you accept or reject, and why."
    )


def build_correction_prompt(errors: List[str]) -> str:
    """Follow-up turn after rejected output"""
    listed = "\n".join(f"- {error}" for error in errors)
    return (
        "The court's validation layer rejected your verdict for these reasons:\n"
        f"{listed}\n\n"
        "Produce a corrected, complete verdict as a single JSON object. Cite only IDs that "
        "appear in the case record, and decide every charge."
    )
