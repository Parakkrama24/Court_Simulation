"""Starting simulations and following them

    POST /api/cases/{case_id}/simulate   start a run (returns at once)
    GET  /api/runs                       every run this server remembers
    GET  /api/runs/{run_id}              status, and the result when finished
    GET  /api/runs/{run_id}/events       events so far (poll with ?after=)
    GET  /api/runs/{run_id}/stream       the same events, as they happen (SSE)
    GET  /api/runs/{run_id}/audit        the audit report
    DELETE /api/runs/{run_id}            forget a finished run
"""

import json
from typing import Any, Dict, Iterator, List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse

from app.llm import LLMError
from app.seed import get_bindings_for_case, get_case_by_id

from ..dependencies import ProviderFactory, get_provider_factory, get_run_manager
from ..runs import RunManager, RunRecord, iter_events
from ..schemas import EventPage, RunDetail, RunStatus, RunSummary, SimulationRequest

router = APIRouter(tags=["simulations"])


def _require_run(manager: RunManager, run_id: str) -> RunRecord:
    record = manager.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'")
    return record


@router.post(
    "/cases/{case_id}/simulate",
    response_model=RunDetail,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a simulation; it runs in the background",
    responses={
        404: {"description": "No such case"},
        409: {"description": "The case cannot be simulated yet"},
        503: {"description": "No LLM provider is available"},
    },
)
def start_simulation(
    case_id: str,
    options: SimulationRequest = SimulationRequest(),
    manager: RunManager = Depends(get_run_manager),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
) -> RunDetail:
    if get_case_by_id(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown case '{case_id}'")
    if not get_bindings_for_case(case_id):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Case '{case_id}' has no element bindings, so the rule engine cannot "
                "evaluate it; only CASE_001 is seeded with them."
            ),
        )

    try:
        provider = provider_factory(options.provider, options.model)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return manager.start(case_id, options, provider).detail()


@router.get("/runs", response_model=List[RunSummary], summary="Every run, newest first")
def list_runs(manager: RunManager = Depends(get_run_manager)) -> List[RunSummary]:
    return [record.summary() for record in manager.list()]


@router.get(
    "/runs/{run_id}",
    response_model=RunDetail,
    summary="One run: its status, and its result once finished",
    responses={404: {"description": "No such run"}},
)
def get_run(run_id: str, manager: RunManager = Depends(get_run_manager)) -> RunDetail:
    return _require_run(manager, run_id).detail()


@router.get(
    "/runs/{run_id}/events",
    response_model=EventPage,
    summary="Events recorded so far",
    responses={404: {"description": "No such run"}},
)
def get_events(
    run_id: str,
    after: int = Query(0, ge=0, description="Return only events after this index"),
    manager: RunManager = Depends(get_run_manager),
) -> EventPage:
    record = _require_run(manager, run_id)
    events = record.events[after:]
    return EventPage(
        run_id=record.run_id,
        status=record.status,
        events=events,
        next_index=after + len(events),
    )


@router.get(
    "/runs/{run_id}/stream",
    summary="Events as they happen (Server-Sent Events)",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}},
        404: {"description": "No such run"},
    },
)
def stream_events(
    run_id: str,
    after: int = Query(0, ge=0),
    manager: RunManager = Depends(get_run_manager),
) -> StreamingResponse:
    """One SSE message per court event, then a final status message

    Each message's event name is the court event type (``AGENT_ARGUMENT``,
    ``JURY_DECISION``, ...), so a browser can listen for the ones it cares
    about; the data is the event itself, as JSON.
    """
    record = _require_run(manager, run_id)

    def emit(name: str, payload: Dict[str, Any]) -> str:
        return f"event: {name}\ndata: {json.dumps(payload)}\n\n"

    def generate() -> Iterator[str]:
        for event in iter_events(record, after=after):
            yield emit(event.get("event_type", "EVENT"), event)
        yield emit(
            "run_completed" if record.status == RunStatus.COMPLETED else "run_failed",
            record.summary().model_dump(mode="json"),
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/runs/{run_id}/audit",
    summary="The audit report of a finished run",
    responses={404: {"description": "No such run, or the run has no audit"}},
)
def get_audit(run_id: str, manager: RunManager = Depends(get_run_manager)) -> Dict[str, Any]:
    record = _require_run(manager, run_id)
    audit = (record.result or {}).get("audit") if record.result else None
    if not audit:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Run '{run_id}' has no audit report"
                f" (status: {record.status.value})"
            ),
        )
    return dict(audit["report"])


@router.delete(
    "/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forget a finished run",
    responses={404: {"description": "No such run"}, 409: {"description": "Still running"}},
)
def delete_run(run_id: str, manager: RunManager = Depends(get_run_manager)) -> Response:
    record = _require_run(manager, run_id)
    if not record.status.is_terminal:
        raise HTTPException(status_code=409, detail=f"Run '{run_id}' is still running")
    manager.remove(run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
