"""TrialRun: everything one trial produced

Both workflows - the linear runner for custom stage plans and the LangGraph
court for the full procedure - produce a ``TrialRun``. The audit, the CLI,
and saved JSON runs all work from it.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.agents.advocate import AdvocateRole, AdvocateTurn
from app.agents.auditor import ProcessAudit
from app.agents.base import add_usage
from app.agents.evidence import EvidenceAnalysis, EvidenceReview
from app.agents.judge import JudgeQuestionRound, JudgeResult
from app.agents.jury import JurorDecision, JuryResult
from app.domain import Argument, Case, CourtMessage, JudgeQuestion
from app.llm import TokenUsage
from app.rules import CaseEvaluation


class TrialRun(BaseModel):
    """Everything produced by one trial"""

    case: Case
    evaluation: CaseEvaluation
    evidence_analysis: Optional[EvidenceAnalysis] = None
    evidence_reviews: List[EvidenceReview] = Field(default_factory=list)
    turns: List[AdvocateTurn] = Field(default_factory=list)
    judge_question_rounds: List[JudgeQuestionRound] = Field(default_factory=list)
    jury_independent: List[JurorDecision] = Field(default_factory=list)
    jury_deliberation: List[JurorDecision] = Field(default_factory=list)
    jury_result: Optional[JuryResult] = None
    judge_jury_agreement: List[Dict[str, Any]] = Field(default_factory=list)
    messages: List[CourtMessage] = Field(default_factory=list)
    judgment: JudgeResult
    audit: Optional[ProcessAudit] = None
    event_history: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def arguments(self) -> List[Argument]:
        """Every argument presented, in order"""
        return [a for turn in self.turns for a in turn.arguments]

    @property
    def prosecution_arguments(self) -> List[Argument]:
        return [a for a in self.arguments if a.agent_id == AdvocateRole.PROSECUTION.agent_id]

    @property
    def defense_arguments(self) -> List[Argument]:
        return [a for a in self.arguments if a.agent_id == AdvocateRole.DEFENSE.agent_id]

    @property
    def judge_questions(self) -> List[JudgeQuestion]:
        """Every question the judge put to the parties, in order"""
        return [q for r in self.judge_question_rounds for q in r.questions]

    @property
    def usage(self) -> TokenUsage:
        """Tokens across every agent call in the trial"""
        total = self.judgment.usage
        for turn in self.turns:
            total = add_usage(total, turn.usage)
        if self.evidence_analysis is not None:
            total = add_usage(total, self.evidence_analysis.usage)
        for review in self.evidence_reviews:
            total = add_usage(total, review.usage)
        for question_round in self.judge_question_rounds:
            total = add_usage(total, question_round.usage)
        for decision in self.jury_independent + self.jury_deliberation:
            total = add_usage(total, decision.usage)
        if self.audit is not None:
            total = add_usage(total, self.audit.usage)
        return total

    @property
    def audit_report(self) -> Optional[Any]:
        """The domain AuditReport, if the trial was audited"""
        return self.audit.report if self.audit is not None else None

    @property
    def jury_verdicts(self) -> List[Any]:
        """Every juror's domain Verdict: independent round, then deliberation"""
        return [d.verdict for d in self.jury_independent + self.jury_deliberation]
