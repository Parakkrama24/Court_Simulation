"""Prompt construction for the Evidence Agent

Bump ``PROMPT_VERSION`` whenever the wording changes.
"""

import json
from typing import Any, Dict, List, Optional, Sequence

from app.domain import Argument, Case, JudgeQuestion
from app.rules import CaseEvaluation, LegalRuleRegistry

from ..record import render_case_record
from .provenance import trace_case_provenance

PROMPT_VERSION = "evidence.v1"

SYSTEM_PROMPT = """\
You are the court's evidence analyst in a court simulation set in the Republic of \
Arandia, a fictional jurisdiction. This is a research simulation: it does not provide \
legal advice and does not determine anyone's real legal rights or obligations.

## You are neutral

You work for the court, not for either party. You analyse what the evidence shows and \
how strongly; you never argue for the prosecution or the defense, and you never say \
whether anyone should be convicted or acquitted - that is the judge's decision alone. \
Report weaknesses on both sides with the same care.

## The record is the only source of truth

Cite facts, evidence, witnesses, and legal rules only by IDs that appear in the record. \
A validation layer checks every ID; output that cites anything not in the record is \
rejected and you will be asked to redo it. The provenance of each evidence item is \
already traced from the record and given to you - use it; do not invent chain-of-custody \
details it does not contain.

## The standards you apply

- E001 Direct evidence establishes a fact directly when reliable; E002 circumstantial \
evidence supports a fact only through inference.
- E003 Witness testimony can be challenged for contradiction, memory limitations, bias, \
opportunity to observe, and personal interest.
- E004 / P005 Conflicting evidence must be identified explicitly.
- P003 A claim is not established because someone asserts it.

A claim's status must follow from what you cite for it:
- established - supported, and nothing in the record contradicts it
- disputed - both supported and contradicted; say in the reasoning which side is stronger
- unsupported - nothing in the record supports it

Write reasoning as concise, self-contained rationales a reader can check against the \
record - not a transcript of your deliberation. Confidence values are numbers from 0.0 \
to 1.0.

Respond with a single JSON object matching the required schema."""


def _record_block(
    case: Case,
    evaluation: CaseEvaluation,
    registry: LegalRuleRegistry,
    arguments: Sequence[Argument] = (),
    evidence_context: Optional[Dict[str, Any]] = None,
    judge_questions: Sequence[JudgeQuestion] = (),
) -> str:
    record = render_case_record(
        case, evaluation, registry, arguments, evidence_context, judge_questions=judge_questions
    )
    if not (evidence_context and "provenance" in evidence_context):
        record["evidence_provenance"] = [p.model_dump() for p in trace_case_provenance(case)]
    return "<case_record>\n" + json.dumps(record, indent=2) + "\n</case_record>\n\n"


def build_analysis_prompt(
    case: Case, evaluation: CaseEvaluation, registry: LegalRuleRegistry
) -> str:
    """User turn for EVIDENCE_ANALYSIS"""
    disputed = [f.fact_id for f in case.facts if f.status.value == "disputed"]
    return _record_block(case, evaluation, registry) + (
        "Task: EVIDENCE_ANALYSIS. Before the parties argue, analyse the record:\n"
        "- claims: the important factual claims in this case - including every disputed "
        f"fact ({', '.join(disputed) or 'none'}) - with their status\n"
        "- evidence: every evidence item exactly once - direct or circumstantial, the facts "
        "it bears on, and any reliability concerns\n"
        "- contradictions: every conflict between items in the record\n"
        "- witnesses: every witness exactly once, rated on the E003 grounds\n"
        "- missing_evidence: evidence the record lacks that bears on a legal element\n"
        "- summary: a short neutral overview"
    )


def build_review_prompt(
    case: Case,
    evaluation: CaseEvaluation,
    registry: LegalRuleRegistry,
    arguments: Sequence[Argument],
    under_review: Sequence[Argument],
    evidence_context: Optional[Dict[str, Any]] = None,
    judge_questions: Sequence[JudgeQuestion] = (),
) -> str:
    """User turn for EVIDENCE_REVIEW (your earlier analysis is under evidence_analysis)"""
    ids = ", ".join(a.argument_id for a in under_review)
    record = _record_block(
        case, evaluation, registry, arguments, evidence_context, judge_questions
    )
    return record + (
        "Task: EVIDENCE_REVIEW. The parties' arguments are under party_arguments. Review "
        f"each of these arguments exactly once: {ids}.\n"
        "For each, decide whether the facts, evidence, and witnesses it cites actually "
        "support its claim - supported, partially_supported, or unsupported - and list the "
        "specific issues: claims that go beyond the cited evidence, citations that "
        "contradict the claim, disputed facts presented as settled, assumptions presented "
        "as facts. Review both parties by the same standard."
    )


def build_correction_prompt(errors: List[str]) -> str:
    """Follow-up turn after rejected output"""
    listed = "\n".join(f"- {error}" for error in errors)
    return (
        "The court's validation layer rejected your output for these reasons:\n"
        f"{listed}\n\n"
        "Produce a corrected, complete response as a single JSON object. Cite only IDs that "
        "appear in the case record."
    )
