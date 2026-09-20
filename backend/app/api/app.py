"""The FastAPI application

    python -m app.cli serve          # then open http://127.0.0.1:8000/docs

Everything under ``/api``; the interactive docs FastAPI generates are the
API reference. CORS allows the frontend's origin from settings.
"""

from typing import Any, List, Optional

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.rules import LegalRuleRegistry
from app.seed import get_all_cases

from .dependencies import get_run_manager, get_settings
from .routers import cases, simulations
from .runs import RunManager
from .schemas import HealthResponse

API_PREFIX = "/api"

DESCRIPTION = """\
A research simulation of a fictional court in the Republic of Arandia.

Read a case and the legal rules, start a simulation, and follow it as it runs.
A simulation is minutes of model calls, so `POST /api/cases/{case_id}/simulate`
returns a run ID at once; follow it with `/events` (polling) or `/stream`
(Server-Sent Events), and read the result from `/runs/{run_id}` when it
finishes.

**Research simulation only.** This system does not provide legal advice or
determine real legal rights or obligations.
"""


def _cors_origins(settings: Optional[Any]) -> List[str]:
    if settings is None:
        return ["http://localhost:3000"]
    origins = list(settings.cors_origins)
    if settings.frontend_url and settings.frontend_url not in origins:
        origins.append(settings.frontend_url)
    return origins


def create_app(settings: Optional[Any] = None) -> FastAPI:
    """Build the application (a factory, so tests can make their own)"""
    settings = settings if settings is not None else get_settings()

    app = FastAPI(
        title="Court Simulation API",
        description=DESCRIPTION,
        version="0.9.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(settings),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(cases.router, prefix=API_PREFIX)
    app.include_router(simulations.router, prefix=API_PREFIX)

    @app.get("/", tags=["meta"], summary="What this is")
    def root() -> dict:
        return {
            "name": "Court Simulation API",
            "docs": "/docs",
            "api": API_PREFIX,
            "disclaimer": (
                "Research simulation only. This system does not provide legal advice "
                "or determine real legal rights or obligations."
            ),
        }

    @app.get("/health", tags=["meta"], response_model=HealthResponse, summary="Liveness")
    def health(manager: RunManager = Depends(get_run_manager)) -> HealthResponse:
        return HealthResponse(
            phase="9 - FastAPI backend",
            cases=len(get_all_cases()),
            rules=len(LegalRuleRegistry()),
            active_runs=manager.active(),
            provider=getattr(settings, "llm_provider", None) if settings else None,
        )

    return app


app = create_app()
