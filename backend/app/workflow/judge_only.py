"""Phase 3 workflow: Case -> Judge Agent -> Decision

A deliberately linear pipeline that validates the LLM integration end to end
without adversarial agents:

    CASE_INITIALIZATION -> RULE_EVALUATION -> JUDGE_DECISION -> CASE_COMPLETE

Every stage appends a structured event to ``event_history``.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.agents.judge import JudgeAgent, JudgeResult
from app.domain import Case
from app.llm import InteractionLog, LLMProvider
from app.rules import CaseEvaluation, LegalRuleRegistry

from .common import WorkflowError, event, prepare_case

__all__ = ["JudgeOnlyRun", "WorkflowError", "run_judge_only"]


class JudgeOnlyRun(BaseModel):
    """Everything produced by one Case -> Judge -> Decision run"""

    case: Case
    evaluation: CaseEvaluation
    result: JudgeResult
    event_history: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)


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
    case, evaluation = prepare_case(case_id, registry, events)

    judge = JudgeAgent(
        provider,
        registry=registry,
        log=log,
        max_attempts=max_attempts,
        strict_engine_alignment=strict_engine_alignment,
    )
    events.append(event("JUDGE_DECISION", "AGENT_STARTED", agent_id=judge.agent_id))
    result = judge.decide(case, evaluation)
    events.append(
        event(
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
    events.append(event("CASE_COMPLETE", "CASE_COMPLETE", case_id=case.case_id))

    return JudgeOnlyRun(case=case, evaluation=evaluation, result=result, event_history=events)
