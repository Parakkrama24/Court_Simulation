"""Prompt construction for the Judge Agent

The system prompt is a fixed, versioned template. The case record and the
rule engine's evaluation are rendered as JSON in the user turn, in a stable
order, so the same case always produces byte-identical prompts. Bump
``PROMPT_VERSION`` whenever the wording changes, so logged interactions stay
comparable across experiments.
"""

import json
from typing import Any, Dict, List, Sequence

from app.domain import Argument, Case, LegalCategory
from app.rules import CaseEvaluation, LegalRuleRegistry

PROMPT_VERSION = "judge.v1"

SYSTEM_PROMPT = """\
You are the presiding judge in a court simulation set in the Republic of Arandia, a \
fictional jurisdiction. This is a research simulation: it does not provide legal advice \
and does not determine anyone's real legal rights or obligations.

Your task is to decide every charge in the case you are given, neutrally and on the \
record alone.

## The record is the only source of truth

The user message contains the complete record: facts, evidence, witnesses, the legal \
rules of Arandia, and a deterministic rule-engine evaluation. Every fact, piece of \
evidence, legal rule, and argument you rely on must be cited by an ID that appears in \
that record. A validation layer checks every ID you cite; output that cites anything \
not in the record is rejected and you will be asked to redo it. Do not introduce facts, \
evidence, witnesses, or laws from outside the record, and do not treat an assumption as \
a fact.

## Principles you must apply

- P001 Presumption of innocence: the defendant is innocent until every required \
element of a charged offense is established.
- P002 Burden of proof: the prosecution carries the burden. An element nobody \
proved is not established.
- P003 Evidence requirement: a statement is not a fact because someone asserts it.
- P004 Reasonable doubt: if substantial uncertainty remains on any required element, \
the decision on that charge is not guilty.
- P005 Evidence consistency: identify and address contradictory evidence explicitly.

## How to decide

Keep six things separate in your output: established facts, disputed facts, applicable \
legal rules, arguments considered, analysis, and the decision.

For each charge, name the offense rule it is decided under and assess every required \
condition of that rule as established, not_established, or doubtful, citing the facts \
and evidence each assessment rests on. A charge may be decided guilty only if every \
required condition is established. Consider any defense rule in the record that could \
apply to the defendant's conduct, and list it under defenses_considered.

Remember whose conduct each rule concerns. The rule-engine evaluation is broken down by \
subject (the party whose conduct is evaluated); for a charge, the relevant subject is \
the defendant.

The rule-engine evaluation is computed deterministically from the record with fixed \
weighting thresholds. Treat it as careful analysis, not as a verdict: you may depart \
from it, but when you do, say so and explain why with cited evidence.

Write reasoning as concise, self-contained rationales a reader can check against the \
record - a few sentences each, not a transcript of your deliberation. Confidence values \
are numbers from 0.0 to 1.0.

Respond with a single JSON object matching the required schema."""


def render_case_record(
    case: Case,
    evaluation: CaseEvaluation,
    registry: LegalRuleRegistry,
    arguments: Sequence[Argument] = (),
) -> Dict[str, Any]:
    """The case record as a JSON-serialisable dict, in a stable order"""
    rule_ids = list(case.applicable_laws)
    rule_ids += [r.rule_id for r in registry.by_category(LegalCategory.PRINCIPLE)]
    rule_ids += [r.rule_id for r in registry.by_category(LegalCategory.EVIDENCE_RULE)]
    rules = [registry.require(rule_id) for rule_id in dict.fromkeys(rule_ids)]

    return {
        "case": {
            "case_id": case.case_id,
            "title": case.title,
            "jurisdiction": case.jurisdiction,
            "case_type": case.case_type.value,
            "summary": case.description,
            "defendant": case.defendant,
            "prosecution": case.prosecution,
            "charges": list(case.charges),
        },
        "facts": [
            {
                "fact_id": f.fact_id,
                "description": f.description,
                "status": f.status.value,
                "source": f.source,
            }
            for f in case.facts
        ],
        "evidence": [
            {
                "evidence_id": e.evidence_id,
                "type": e.type.value,
                "description": e.description,
                "source": e.source,
                "supports_facts": list(e.supports),
                "contradicts_facts": list(e.contradicts),
                "reliability": e.reliability,
            }
            for e in case.evidence
        ],
        "witnesses": [
            {
                "witness_id": w.witness_id,
                "name": w.name,
                "statement": w.statement,
                "reliability_factors": dict(w.reliability_factors),
                "related_evidence": list(w.related_evidence),
            }
            for w in case.witnesses
        ],
        "legal_rules": [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "category": r.category.value,
                "description": r.description,
                "conditions": [
                    {
                        "condition_id": c.id,
                        "description": c.description,
                        "required": c.required,
                        **({"depends_on_rule": c.depends_on_rule} if c.depends_on_rule else {}),
                    }
                    for c in r.conditions
                ],
                "effect": r.effect,
            }
            for r in rules
        ],
        "rule_engine_evaluation": _render_evaluation(evaluation),
        "party_arguments": [
            {
                "argument_id": a.argument_id,
                "agent_id": a.agent_id,
                "claim": a.claim,
                "evidence_ids": list(a.evidence_ids),
                "law_ids": list(a.law_ids),
                "reasoning": a.reasoning,
            }
            for a in arguments
        ],
    }


def _render_evaluation(evaluation: CaseEvaluation) -> Dict[str, Any]:
    return {
        "policy": {
            "satisfaction_threshold": evaluation.policy.satisfaction_threshold,
            "dispute_threshold": evaluation.policy.dispute_threshold,
        },
        "rules": [
            {
                "rule_id": r.rule_id,
                "subject": r.subject,
                "status": r.status.value,
                "reasoning": r.reasoning,
                "conditions": [
                    {
                        "condition_id": c.condition_id,
                        "status": c.status.value,
                        "support_strength": round(c.support_strength, 3),
                        "contradiction_strength": round(c.contradiction_strength, 3),
                        "supporting_fact_ids": list(c.supporting_fact_ids),
                        "supporting_evidence_ids": list(c.supporting_evidence_ids),
                        "contradicting_fact_ids": list(c.contradicting_fact_ids),
                        "contradicting_evidence_ids": list(c.contradicting_evidence_ids),
                    }
                    for c in r.conditions
                ],
            }
            for r in evaluation.rule_evaluations
            if r.conditions
        ],
        "witness_reliability": [
            {
                "witness_id": w.witness_id,
                "score": w.reliability_score,
                "challenge_grounds": list(w.challenge_grounds),
            }
            for w in evaluation.witness_assessments
        ],
        "conflicts": [
            {k: v for k, v in c.items() if k != "description"} | {"note": c["description"]}
            for c in evaluation.conflicting_evidence
        ],
        "unevaluated_rules": list(evaluation.unevaluated_rules),
    }


def build_user_prompt(
    case: Case,
    evaluation: CaseEvaluation,
    registry: LegalRuleRegistry,
    arguments: Sequence[Argument] = (),
) -> str:
    """The first user turn: the record, then the task"""
    record = render_case_record(case, evaluation, registry, arguments)
    charges = ", ".join(case.charges) if case.charges else "(none)"
    argument_note = (
        "Party arguments are included under party_arguments."
        if arguments
        else "No party arguments have been presented at this stage; "
        "arguments_considered must be an empty list."
    )
    return (
        "<case_record>\n"
        + json.dumps(record, indent=2, sort_keys=False)
        + "\n</case_record>\n\n"
        + f"Decide each charge against the defendant, {case.defendant}: {charges}. "
        + argument_note
    )


def build_correction_prompt(errors: List[str]) -> str:
    """The follow-up turn after a rejected decision"""
    listed = "\n".join(f"- {error}" for error in errors)
    return (
        "The court's validation layer rejected your decision for these reasons:\n"
        f"{listed}\n\n"
        "Produce a corrected, complete decision as a single JSON object. Cite only IDs "
        "that appear in the case record, and address every charge and every required "
        "element."
    )
