"""Tests for starting simulations and following them"""

import json
import threading

import pytest

from app.api.runs import RunRecord, iter_events
from app.api.schemas import RunStatus, SimulationRequest
from app.llm import LLMConfigurationError, LLMProvider, LLMRequest, LLMResponse, ScriptedProvider

from .conftest import debate_steps, evidence_steps, judgment, run_to_completion, start


class BlockingProvider(LLMProvider):
    """Waits for a release before answering, so a test can watch a run in flight"""

    name = "blocking"

    def __init__(self, release: threading.Event) -> None:
        super().__init__("blocking-model")
        self.release = release
        self.called = threading.Event()

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.called.set()
        self.release.wait(timeout=10)
        return LLMResponse(text=json.dumps(judgment()), provider=self.name, model=self.model)


class TestStartingARun:
    def test_a_run_starts_immediately_and_finishes_in_the_background(self, client, manager):
        response = start(client)
        assert response.status_code == 202
        body = response.json()
        assert body["status"] in ("queued", "running")
        assert body["result"] is None
        assert body["options"]["mode"] == "court"

        manager.wait_for(body["run_id"], timeout=30)
        detail = client.get(f"/api/runs/{body['run_id']}").json()
        assert detail["status"] == "completed"
        assert detail["current_stage"] == "CASE_COMPLETE"
        assert detail["error"] is None
        assert detail["finished_at"] > detail["started_at"]

    def test_the_result_is_the_whole_trial(self, client, manager):
        detail = run_to_completion(client, manager)
        result = detail["result"]
        assert result["judgment"]["verdict"]["decision"] == (
            "burglary: not_guilty; assault: not_guilty"
        )
        assert len(result["turns"]) == 8
        assert result["audit"]["report"]["metadata"]["overall_status"] == "clean"
        assert detail["usage"] == {
            "input_tokens": detail["usage"]["input_tokens"],
            "output_tokens": detail["usage"]["output_tokens"],
            "calls": 9,
        }

    def test_defaults_need_no_body(self, client):
        response = client.post("/api/cases/CASE_001/simulate")
        assert response.status_code == 202
        options = response.json()["options"]
        assert options == SimulationRequest().model_dump(mode="json")

    def test_judge_mode(self, make_client, manager):
        client = make_client([judgment(considered=[])])  # no arguments in judge-only mode
        detail = run_to_completion(client, manager, {"mode": "judge"})
        assert detail["status"] == "completed"
        assert detail["result"]["result"]["verdict"]["charges"] == ["burglary", "assault"]
        assert [e["event_type"] for e in detail["result"]["event_history"]][0] == "CASE_LOADED"

    def test_evidence_mode(self, make_client, manager):
        client = make_client(evidence_steps())
        detail = run_to_completion(client, manager, {"mode": "evidence"})
        assert detail["status"] == "completed"
        assert len(detail["result"]["analysis"]["output"]["claims"]) == 4

    def test_runs_are_listed_newest_first(self, client, manager):
        first = start(client).json()["run_id"]
        manager.wait_for(first, timeout=30)
        second = start(client).json()["run_id"]
        manager.wait_for(second, timeout=30)
        assert [r["run_id"] for r in client.get("/api/runs").json()][:2] == [second, first]


class TestFollowingARun:
    def test_events_can_be_paged(self, client, manager):
        detail = run_to_completion(client, manager)
        run_id = detail["run_id"]

        first = client.get(f"/api/runs/{run_id}/events").json()
        assert first["status"] == "completed"
        assert first["events"][0]["event_type"] == "CASE_LOADED"
        assert first["next_index"] == len(first["events"])

        rest = client.get(f"/api/runs/{run_id}/events", params={"after": 2}).json()
        assert rest["events"] == first["events"][2:]
        assert rest["next_index"] == first["next_index"]

        nothing_new = client.get(
            f"/api/runs/{run_id}/events", params={"after": first["next_index"]}
        ).json()
        assert nothing_new["events"] == []

    def test_stream_is_server_sent_events(self, client, manager):
        detail = run_to_completion(client, manager)
        with client.stream("GET", f"/api/runs/{detail['run_id']}/stream") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["cache-control"] == "no-cache"
            body = "".join(response.iter_text())

        names = [line[len("event: ") :] for line in body.splitlines() if line.startswith("event:")]
        assert names[0] == "CASE_LOADED"
        assert "JUDGE_DECISION" in names
        assert names[-1] == "run_completed"
        data_lines = [line for line in body.splitlines() if line.startswith("data:")]
        payloads = [json.loads(line[len("data: ") :]) for line in data_lines]
        assert payloads[0]["stage"] == "CASE_INITIALIZATION"
        assert payloads[-1]["status"] == "completed"

    def test_stream_follows_a_run_that_is_still_going(self):
        """iter_events yields what is there, waits for more, and stops at the end"""
        record = RunRecord(run_id="r1", case_id="CASE_001", options=SimulationRequest())
        record.status = RunStatus.RUNNING
        record.record_event({"stage": "CASE_INITIALIZATION", "event_type": "CASE_LOADED"})

        def finish() -> None:
            record.record_event({"stage": "JUDGE_DECISION", "event_type": "JUDGE_DECISION"})
            record.status = RunStatus.COMPLETED

        threading.Timer(0.2, finish).start()
        seen = [event["event_type"] for event in iter_events(record, poll=0.05, timeout=5)]
        assert seen == ["CASE_LOADED", "JUDGE_DECISION"]

    def test_audit_report(self, client, manager):
        detail = run_to_completion(client, manager)
        report = client.get(f"/api/runs/{detail['run_id']}/audit").json()
        assert report["audit_id"] == "AUD_CASE_001"
        assert report["metadata"]["overall_status"] == "clean"
        assert report["metadata"]["deterministic_only"] is True

    def test_no_audit_when_it_was_not_run(self, client, manager):
        detail = run_to_completion(client, manager, {"audit": False})
        response = client.get(f"/api/runs/{detail['run_id']}/audit")
        assert response.status_code == 404
        assert "has no audit report" in response.json()["detail"]

    def test_unknown_run(self, client):
        for path in ("", "/events", "/audit", "/stream"):
            assert client.get(f"/api/runs/nope{path}").status_code == 404


class TestFailures:
    def test_a_failing_run_reports_why(self, make_client, manager):
        client = make_client(["not json"] * 3)
        detail = run_to_completion(client, manager)
        assert detail["status"] == "failed"
        assert "No valid" in detail["error"]
        assert detail["result"] is None
        assert client.get(f"/api/runs/{detail['run_id']}/audit").status_code == 404

    def test_unknown_case(self, client):
        response = client.post("/api/cases/CASE_404/simulate", json={})
        assert response.status_code == 404
        assert "Unknown case" in response.json()["detail"]

    def test_a_case_without_bindings_cannot_be_simulated(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routers.simulations.get_bindings_for_case", lambda _: [])
        response = client.post("/api/cases/CASE_001/simulate", json={})
        assert response.status_code == 409
        assert "no element bindings" in response.json()["detail"]

    def test_no_provider_configured(self, make_client):
        def broken(name, model):
            raise LLMConfigurationError("No LLM provider is configured.")

        client = make_client(provider_factory=broken)
        response = client.post("/api/cases/CASE_001/simulate", json={})
        assert response.status_code == 503
        assert "No LLM provider is configured" in response.json()["detail"]

    @pytest.mark.parametrize(
        "body,field",
        [({"jurors": 0}, "jurors"), ({"question_rounds": 9}, "question_rounds")],
    )
    def test_options_are_validated(self, client, body, field):
        response = client.post("/api/cases/CASE_001/simulate", json=body)
        assert response.status_code == 422
        assert field in json.dumps(response.json())


class TestDeletingRuns:
    def test_forget_a_finished_run(self, client, manager):
        detail = run_to_completion(client, manager)
        assert client.delete(f"/api/runs/{detail['run_id']}").status_code == 204
        assert client.get(f"/api/runs/{detail['run_id']}").status_code == 404
        assert client.delete(f"/api/runs/{detail['run_id']}").status_code == 404

    def test_a_running_run_is_not_deleted(self, make_client, manager):
        release = threading.Event()
        provider = BlockingProvider(release)
        client = make_client(provider_factory=lambda name, model: provider)
        run_id = start(client, {"mode": "judge"}).json()["run_id"]
        assert provider.called.wait(timeout=10)

        response = client.delete(f"/api/runs/{run_id}")
        assert response.status_code == 409
        assert "still running" in response.json()["detail"]
        assert client.get("/health").json()["active_runs"] == 1

        release.set()
        manager.wait_for(run_id, timeout=30)
        assert client.delete(f"/api/runs/{run_id}").status_code == 204


class TestProviderChoice:
    def test_the_request_can_name_a_provider_and_model(self, make_client, manager):
        asked = {}

        def factory(name, model):
            asked["name"], asked["model"] = name, model
            return ScriptedProvider(debate_steps())

        client = make_client(provider_factory=factory)
        run_to_completion(client, manager, {"provider": "local", "model": "llama3.1"})
        assert asked == {"name": "local", "model": "llama3.1"}

    def test_omitting_them_uses_the_server_default(self, make_client, manager):
        asked = {}

        def factory(name, model):
            asked["name"], asked["model"] = name, model
            return ScriptedProvider(debate_steps())

        client = make_client(provider_factory=factory)
        run_to_completion(client, manager)
        assert asked == {"name": None, "model": None}
