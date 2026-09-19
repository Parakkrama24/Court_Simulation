"""The case record as agents see it

Every agent receives the same authoritative record, rendered as JSON in a
stable order so identical inputs always produce byte-identical prompts. The
record includes the rule engine's evaluation and, once the debate starts, the
arguments presented so far - each with the system-assigned ID other agents
use to refer to it - and, when the Evidence Agent has run, its neutral
analysis and its reviews of the arguments.
"""

from typing import Any, Dict, Optional, Sequence

from app.domain import Argument, Case, JudgeQuestion, LegalCategory
from app.rules import CaseEvaluation, LegalRuleRegistry


def render_argument(argument: Argument) -> Dict[str, Any]:
    """One argument with every citation it carries"""
    meta = argument.metadata
    return {
        "argument_id": argument.argument_id,
        "party": argument.agent_id,
        "stage": meta.get("stage", ""),
        "charges": list(meta.get("charges", [])),
        "elements": list(meta.get("elements", [])),
        "claim": argument.claim,
        "fact_ids": list(argument.fact_ids),
        "evidence_ids": list(argument.evidence_ids),
        "witness_ids": list(argument.witness_ids),
        "law_ids": list(argument.law_ids),
        "responds_to": list(argument.counter_argument_ids),
        "assumptions": list(meta.get("assumptions", [])),
        "reasoning": argument.reasoning,
        "confidence": argument.confidence,
    }


def render_case_record(
    case: Case,
    evaluation: CaseEvaluation,
    registry: LegalRuleRegistry,
    arguments: Sequence[Argument] = (),
    evidence_context: Optional[Dict[str, Any]] = None,
    jury_context: Optional[Dict[str, Any]] = None,
    judge_questions: Sequence[JudgeQuestion] = (),
) -> Dict[str, Any]:
    """The case record as a JSON-serialisable dict, in a stable order

    ``evidence_context`` is the Evidence Agent's work as plain data (see
    ``app.agents.evidence.evidence_context``); it is added under
    ``evidence_analysis`` when present. ``jury_context`` is the jury's
    tallied result (see ``app.agents.jury.jury_context``), added under
    ``jury`` - only the judge is ever given it. ``judge_questions`` are the
    questions the judge has put to the parties, added when there are any.
    """
    rule_ids = list(case.applicable_laws)
    rule_ids += [r.rule_id for r in registry.by_category(LegalCategory.PRINCIPLE)]
    rule_ids += [r.rule_id for r in registry.by_category(LegalCategory.EVIDENCE_RULE)]
    rules = [registry.require(rule_id) for rule_id in dict.fromkeys(rule_ids)]

    record: Dict[str, Any] = {
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
        "party_arguments": [render_argument(a) for a in arguments],
    }
    if evidence_context is not None:
        record["evidence_analysis"] = evidence_context
    if jury_context is not None:
        record["jury"] = jury_context
    if judge_questions:
        record["judge_questions"] = [render_question(q) for q in judge_questions]
    return record


def render_question(question: JudgeQuestion) -> Dict[str, Any]:
    """One question from the judge, as the parties and the court see it"""
    return {
        "question_id": question.question_id,
        "round": question.round,
        "addressed_to": question.addressed_to,
        "about_arguments": list(question.argument_ids),
        "question": question.question,
        "reason": question.reason,
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
