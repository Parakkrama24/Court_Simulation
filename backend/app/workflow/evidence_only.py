"""Evidence analysis on its own: Case -> Evidence Agent

    CASE_INITIALIZATION -> RULE_EVALUATION -> EVIDENCE_ANALYSIS

One model call. Useful for studying the Evidence Agent in isolation, and for
inspecting a case before running a full trial.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.agents.evidence import EvidenceAgent, EvidenceAnalysis
from app.domain import Case, CourtStage
from app.llm import InteractionLog, LLMProvider
from app.rules import CaseEvaluation, LegalRuleRegistry

from .common import event, prepare_case


class EvidenceRun(BaseModel):
    """Everything produced by one evidence-analysis run"""

    case: Case
    evaluation: CaseEvaluation
    analysis: EvidenceAnalysis
    event_history: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)


def run_evidence_analysis(
    case_id: str,
    provider: LLMProvider,
    log: Optional[InteractionLog] = None,
    max_attempts: int = 3,
) -> EvidenceRun:
    """Analyse one seeded case's evidence"""
    events: List[Dict[str, Any]] = []
    registry = LegalRuleRegistry()
    case, evaluation = prepare_case(case_id, registry, events)

    analyst = EvidenceAgent(provider, registry=registry, log=log, max_attempts=max_attempts)
    stage = CourtStage.EVIDENCE_ANALYSIS.value
    events.append(event(stage, "AGENT_STARTED", agent_id=analyst.agent_id))
    analysis = analyst.analyze(case, evaluation)
    events.append(
        event(
            stage,
            "EVIDENCE_ANALYZED",
            agent_id=analyst.agent_id,
            claims=len(analysis.output.claims),
            contradictions=len(analysis.output.contradictions),
            missing_evidence=len(analysis.output.missing_evidence),
            flags=len(analysis.flags),
            attempts=len(analysis.attempts),
            rejected_attempts=analysis.rejected_attempts,
        )
    )
    return EvidenceRun(case=case, evaluation=evaluation, analysis=analysis, event_history=events)
