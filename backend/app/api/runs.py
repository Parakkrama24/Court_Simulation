"""Simulation runs: start one, follow it, read its result

A trial is minutes of blocking model calls, so a request never waits for one.
``POST /simulate`` starts the run in a background thread and returns its ID;
the client then polls ``/events`` or subscribes to ``/stream``, and reads the
result from ``/runs/{id}`` when the status is terminal.

Runs live in memory. Restarting the server forgets them - persistence is a
later phase - but a finished run's JSON is the same ``TrialRun`` the CLI
writes, so a client can save it.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agents.base import AgentError
from app.domain import utc_now
from app.llm import InteractionLog, LLMError, LLMProvider
from app.workflow import WorkflowError, run_court, run_evidence_analysis, run_judge_only

from .schemas import RunDetail, RunMode, RunStatus, RunSummary, SimulationRequest

DEFAULT_MAX_RUNS = 50


@dataclass
class RunRecord:
    """One simulation run and everything known about it so far"""

    run_id: str
    case_id: str
    options: SimulationRequest
    status: RunStatus = RunStatus.QUEUED
    created_at: str = field(default_factory=lambda: utc_now().isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    current_stage: str = ""
    error: Optional[str] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    usage: Dict[str, int] = field(default_factory=dict)
    log: InteractionLog = field(default_factory=InteractionLog)
    _thread: Optional[threading.Thread] = None

    @property
    def mode(self) -> RunMode:
        return self.options.mode

    def record_event(self, event: Dict[str, Any]) -> None:
        self.events.append(event)
        self.current_stage = event.get("stage", self.current_stage)

    def summary(self) -> RunSummary:
        return RunSummary(
            run_id=self.run_id,
            case_id=self.case_id,
            mode=self.mode,
            status=self.status,
            current_stage=self.current_stage,
            event_count=len(self.events),
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            error=self.error,
        )

    def detail(self) -> RunDetail:
        return RunDetail(
            **self.summary().model_dump(),
            options=self.options,
            result=self.result,
            usage=dict(self.usage),
        )


class RunManager:
    """Starts runs, keeps them, and hands them back"""

    def __init__(self, max_runs: int = DEFAULT_MAX_RUNS) -> None:
        self._runs: Dict[str, RunRecord] = {}
        self._lock = threading.Lock()
        self.max_runs = max_runs

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def get(self, run_id: str) -> Optional[RunRecord]:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> List[RunRecord]:
        """Newest first"""
        with self._lock:
            return sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)

    def active(self) -> int:
        with self._lock:
            return sum(1 for r in self._runs.values() if not r.status.is_terminal)

    def remove(self, run_id: str) -> bool:
        with self._lock:
            return self._runs.pop(run_id, None) is not None

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------

    def start(
        self, case_id: str, options: SimulationRequest, provider: LLMProvider
    ) -> RunRecord:
        """Start a run in the background and return it immediately"""
        record = RunRecord(run_id=uuid.uuid4().hex[:12], case_id=case_id, options=options)
        with self._lock:
            self._prune()
            self._runs[record.run_id] = record

        thread = threading.Thread(
            target=self._execute,
            args=(record, provider),
            name=f"court-run-{record.run_id}",
            daemon=True,
        )
        record._thread = thread
        thread.start()
        return record

    def wait_for(self, run_id: str, timeout: float = 30.0) -> Optional[RunRecord]:
        """Block until a run finishes (for tests and scripts, not for requests)"""
        record = self.get(run_id)
        if record is None:
            return None
        if record._thread is not None:
            record._thread.join(timeout)
        return record

    def _prune(self) -> None:
        """Forget the oldest finished runs once there are too many"""
        finished = [r for r in self._runs.values() if r.status.is_terminal]
        excess = len(self._runs) - self.max_runs
        for record in sorted(finished, key=lambda r: r.created_at)[: max(0, excess)]:
            self._runs.pop(record.run_id, None)

    def _execute(self, record: RunRecord, provider: LLMProvider) -> None:
        record.status = RunStatus.RUNNING
        record.started_at = utc_now().isoformat()
        options = record.options
        try:
            if options.mode == RunMode.COURT:
                run = run_court(
                    record.case_id,
                    provider,
                    evidence=options.evidence,
                    cross_examination=options.cross_examination,
                    judge_questions=options.judge_questions,
                    max_question_rounds=options.question_rounds,
                    jury=options.jury,
                    jurors=options.jurors,
                    deliberation=options.deliberation,
                    jury_rule=options.jury_rule,
                    audit=options.audit,
                    audit_agent=options.audit_agent,
                    log=record.log,
                    max_attempts=options.max_attempts,
                    strict_engine_alignment=options.strict_engine_alignment,
                    on_event=record.record_event,
                )
            elif options.mode == RunMode.JUDGE:
                run = run_judge_only(
                    record.case_id,
                    provider,
                    log=record.log,
                    max_attempts=options.max_attempts,
                    strict_engine_alignment=options.strict_engine_alignment,
                )
            else:
                run = run_evidence_analysis(
                    record.case_id,
                    provider,
                    log=record.log,
                    max_attempts=options.max_attempts,
                )

            # Single-call modes have no live events; take their history at the end.
            if options.mode != RunMode.COURT:
                for event in run.event_history:
                    record.record_event(event)

            record.result = run.model_dump(mode="json")
            usage = record.log.total_usage
            record.usage = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "calls": len(record.log.records),
            }
            record.status = RunStatus.COMPLETED
        except (WorkflowError, AgentError, LLMError, ValueError) as exc:
            record.status = RunStatus.FAILED
            record.error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # unexpected: still report it rather than hang the run
            record.status = RunStatus.FAILED
            record.error = f"Unexpected {type(exc).__name__}: {exc}"
        finally:
            record.finished_at = utc_now().isoformat()


def iter_events(record: RunRecord, after: int = 0, poll: float = 0.2, timeout: float = 900.0):
    """Yield events from ``after`` onwards until the run finishes

    Polls the record's own list: simple, and it cannot lose an event the way a
    queue can if a subscriber joins late.
    """
    index = max(0, after)
    deadline = time.monotonic() + timeout
    while True:
        while index < len(record.events):
            yield record.events[index]
            index += 1
        if record.status.is_terminal:
            return
        if time.monotonic() > deadline:
            return
        time.sleep(poll)
