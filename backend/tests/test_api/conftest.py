"""Fixtures for API tests

Every test drives the API with scripted agents: no network, no API key. The
provider factory is a FastAPI dependency, so a test supplies its own without
touching the routers.
"""

import copy
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.api import create_app, get_provider_factory, get_run_manager
from app.llm import ScriptedProvider

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "test_agents"))

from conftest import (  # noqa: E402  (shared agent fixtures)
    VALID_ANALYSIS,
    VALID_DECISION,
    defense_turn,
    prosecution_turn,
)

# A court run with the optional stages off: 8 debate turns, then the judgment.
MINIMAL_OPTIONS = {
    "evidence": False,
    "cross_examination": False,
    "judge_questions": False,
    "jury": False,
    "audit": True,
    "audit_agent": False,
}


def judgment(considered: Optional[List[str]] = None) -> dict:
    """A decision; with no arguments on the record it cites none (judge-only mode)"""
    decision = copy.deepcopy(VALID_DECISION)
    decision["arguments_considered"] = list(
        considered if considered is not None else ["PR-OPEN-1", "DF-OPEN-1"]
    )
    return decision


def debate_steps() -> List[Any]:
    """The nine scripted responses a minimal court run consumes"""
    return [
        prosecution_turn(), defense_turn(),                            # openings
        prosecution_turn(), defense_turn(),                            # arguments
        prosecution_turn(["DF-ARG-1"]), defense_turn(["PR-REB-1"]),    # rebuttals
        prosecution_turn(), defense_turn(),                            # closings
        judgment(),
    ]


def evidence_steps() -> List[Any]:
    return [VALID_ANALYSIS]


@pytest.fixture
def manager():
    """The process-wide run manager, emptied after each test"""
    manager = get_run_manager()
    yield manager
    for record in manager.list():
        manager.remove(record.run_id)


@pytest.fixture
def make_client(manager) -> Callable[..., TestClient]:
    """Build a client whose simulations use the steps (or factory) given"""

    def build(
        steps: Optional[List[Any]] = None,
        provider_factory: Optional[Callable[..., Any]] = None,
    ) -> TestClient:
        app = create_app()
        factory = provider_factory or (lambda name, model: ScriptedProvider(list(steps or [])))
        app.dependency_overrides[get_provider_factory] = lambda: factory
        return TestClient(app)

    return build


@pytest.fixture
def client(make_client) -> TestClient:
    """A client whose runs complete: the minimal court run"""
    return make_client(debate_steps())


def start(client: TestClient, options: Optional[dict] = None, case_id: str = "CASE_001"):
    body = dict(MINIMAL_OPTIONS)
    body.update(options or {})
    return client.post(f"/api/cases/{case_id}/simulate", json=body)


def run_to_completion(client: TestClient, manager, options: Optional[dict] = None) -> dict:
    """Start a run, wait for it, and return its detail"""
    response = start(client, options)
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    manager.wait_for(run_id, timeout=30)
    return client.get(f"/api/runs/{run_id}").json()
