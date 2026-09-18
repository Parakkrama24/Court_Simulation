"""Phase 3 workflow: Case -> Judge Agent -> Decision

A deliberately linear pipeline that validates the LLM integration end to end
before any adversarial agents exist:

    CASE_INITIALIZATION -> RULE_EVALUATION -> JUDGE_DECISION -> CASE_COMPLETE

Every stage appends a structured event to ``event_history``. The full court
procedure, as a LangGraph state machine, replaces this in a later phase.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.agents.judge import JudgeAgent, JudgeResult
from app.domain import Case, utc_now
from app.llm import InteractionLog, LLMProvider
from app.rules import CaseEvaluation, LegalRuleRegistry, ReferenceValidator, RuleEngine
from app.seed import get_bindings_for_case, get_case_by_id


class WorkflowError(Exception):
    """The workflow could not run to completion"""


class JudgeOnlyRun(BaseModel):
    """Everything produced by one Case -> Judge -> Decision run"""

    case: Case
    evaluation: CaseEvaluation
    result: JudgeResult
    event_history: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)


def _event(stage: str, event_type: str, **details: Any) -> Dict[str, Any]:
    return {
        "stage": stage,
        "event_type": event_type,
        "timestamp": utc_now().isoformat(),
        **details,
    }


def run_judge_only(
    case_id: str,
    provider: LLMProvider,
    log: Optional[InteractionLog] = None,
    max_attempts: int = 3,
    strict_engine_alignment: bool = False,
) -> JudgeOnlyRun:
    """Run the Phase 3 pipeline for one seeded case"""
    events: List[Dict[str, Any]] = []
    registry = LegalRuleRegistry()

    case = get_case_by_id(case_id)
    if case is None:
        raise WorkflowError(f"Unknown case '{case_id}'")
    events.append(
        _event(
            "CASE_INITIALIZATION",
            "CASE_LOADED",
            case_id=case.case_id,
            facts=len(case.facts),
            evidence=len(case.evidence),
            witnesses=len(case.witnesses),
            charges=list(case.charges),
        )
    )

    bindings = get_bindings_for_case(case.case_id)
    binding_check = ReferenceValidator(case, registry).validate_bindings(bindings)
    if not binding_check.valid:
        raise WorkflowError(
            f"Seeded bindings for {case.case_id} are invalid: {'; '.join(binding_check.messages)}"
        )

    evaluation = RuleEngine(registry).evaluate_case(case, bindings)
    events.append(
        _event(
            "RULE_EVALUATION",
            "RULES_EVALUATED",
            bindings=len(bindings),
            rules={f"{r.rule_id}/{r.subject}": r.status.value for r in evaluation.rule_evaluations},
            unevaluated_rules=list(evaluation.unevaluated_rules),
        )
    )

    judge = JudgeAgent(
        provider,
        registry=registry,
        log=log,
        max_attempts=max_attempts,
        strict_engine_alignment=strict_engine_alignment,
    )
    events.append(_event("JUDGE_DECISION", "AGENT_STARTED", agent_id=judge.agent_id))
    result = judge.decide(case, evaluation)
    events.append(
        _event(
            "JUDGE_DECISION",
            "JUDGE_DECISION",
            agent_id=judge.agent_id,
            verdict_id=result.verdict.verdict_id,
            decision=result.verdict.decision,
            attempts=len(result.attempts),
            rejected_attempts=result.rejected_attempts,
            divergences=len(result.divergences),
        )
    )
    events.append(_event("CASE_COMPLETE", "CASE_COMPLETE", case_id=case.case_id))

    return JudgeOnlyRun(case=case, evaluation=evaluation, result=result, event_history=events)
