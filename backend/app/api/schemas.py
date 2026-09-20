"""Request and response models for the HTTP API

These are the API's own contract, separate from the domain models: a client
should not have to change because an internal model moved. Full trial output
is returned as the serialised ``TrialRun``, which is the same JSON the CLI
writes with ``--json``.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.agents.jury import JuryRule


class RunMode(str, Enum):
    """What to run for a case"""

    COURT = "court"  # the full spec section 14 procedure
    JUDGE = "judge"  # case -> judge -> decision (one call)
    EVIDENCE = "evidence"  # the Evidence Agent's analysis only (one call)


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (RunStatus.COMPLETED, RunStatus.FAILED)


class SimulationRequest(BaseModel):
    """Options for starting a simulation

    Every field has a default, so ``POST .../simulate`` with an empty body
    runs the full procedure with the server's configured provider.
    """

    mode: RunMode = RunMode.COURT
    provider: Optional[str] = Field(
        default=None, description="anthropic, openai, or local; server default if omitted"
    )
    model: Optional[str] = Field(default=None, description="Override the provider's model")

    evidence: bool = True
    cross_examination: bool = True
    judge_questions: bool = True
    question_rounds: int = Field(default=1, ge=0, le=5)
    jury: bool = True
    jurors: int = Field(default=3, ge=1, le=12)
    deliberation: bool = True
    jury_rule: JuryRule = JuryRule.UNANIMOUS
    audit: bool = True
    audit_agent: bool = True
    max_attempts: int = Field(default=3, ge=1, le=5)
    strict_engine_alignment: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mode": "court",
                "provider": "anthropic",
                "jurors": 3,
                "question_rounds": 1,
            }
        }
    )


class RunSummary(BaseModel):
    """A simulation run, without its result"""

    run_id: str
    case_id: str
    mode: RunMode
    status: RunStatus
    current_stage: str = ""
    event_count: int = 0
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None


class RunDetail(RunSummary):
    """A run with its options and, once finished, its result"""

    options: SimulationRequest
    result: Optional[Dict[str, Any]] = Field(
        default=None, description="The serialised run: a TrialRun, JudgeOnlyRun, or EvidenceRun"
    )
    usage: Dict[str, int] = Field(default_factory=dict)


class EventPage(BaseModel):
    """Events recorded so far, for polling clients"""

    run_id: str
    status: RunStatus
    events: List[Dict[str, Any]]
    next_index: int = Field(..., description="Pass as ?after= to fetch only newer events")


class CaseSummary(BaseModel):
    """One seeded case, at a glance"""

    case_id: str
    title: str
    defendant: str
    charges: List[str]
    case_type: str
    jurisdiction: str
    facts: int
    evidence: int
    witnesses: int
    applicable_laws: List[str]
    runnable: bool = Field(
        ..., description="Whether the case has the element bindings a simulation needs"
    )


class CaseDetail(BaseModel):
    """Everything about a case the UI needs before a trial runs"""

    case: Dict[str, Any]
    rule_evaluation: Dict[str, Any]
    evidence_provenance: List[Dict[str, Any]]
    bindings: int
    runnable: bool


class RuleDetail(BaseModel):
    """One legal rule of the jurisdiction"""

    rule_id: str
    name: str
    category: str
    description: str
    conditions: List[Dict[str, Any]]
    effect: str
    jurisdiction: str


class HealthResponse(BaseModel):
    status: str = "ok"
    phase: str
    cases: int
    rules: int
    active_runs: int
    provider: Optional[str] = Field(
        default=None, description="The server's configured LLM provider"
    )


class ErrorResponse(BaseModel):
    detail: str
