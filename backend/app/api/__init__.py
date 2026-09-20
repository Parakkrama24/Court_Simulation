"""HTTP API for the court simulation (Phase 9)

``create_app()`` builds the FastAPI application; ``app`` is a ready instance
for ``uvicorn app.api:app``. Routers live under ``/api``; the OpenAPI docs at
``/docs`` are the reference.
"""

from .app import API_PREFIX, app, create_app
from .dependencies import get_provider_factory, get_run_manager, get_settings
from .runs import RunManager, RunRecord
from .schemas import (
    CaseDetail,
    CaseSummary,
    EventPage,
    RunDetail,
    RunMode,
    RunStatus,
    RunSummary,
    SimulationRequest,
)

__all__ = [
    "API_PREFIX",
    "app",
    "create_app",
    "get_provider_factory",
    "get_run_manager",
    "get_settings",
    "RunManager",
    "RunRecord",
    "CaseDetail",
    "CaseSummary",
    "EventPage",
    "RunDetail",
    "RunMode",
    "RunStatus",
    "RunSummary",
    "SimulationRequest",
]
