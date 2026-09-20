# Phase 9 Implementation Complete ✅

## Overview

**Phase 9: FastAPI Backend** has been implemented and tested.

**Completion Date**: 2026-09-20
**Status**: ✅ All tests passing (549/549)
**Next Phase**: Phase 10 - Frontend Visualization

The simulation is now reachable over HTTP, with the streaming spec §21 asks
for. The frontend in Phase 10 has an API to talk to.

```bash
cd backend
pip install -r requirements.txt
python -m app.cli serve          # http://127.0.0.1:8000/docs
```

---

## What Was Built

### 1. The Endpoints

| Method | Path | |
|---|---|---|
| GET | `/` | what this is, and where the docs are |
| GET | `/health` | liveness, case and rule counts, active runs, configured provider |
| GET | `/api/cases` | the seeded cases, with whether each can be simulated |
| GET | `/api/cases/{case_id}` | the record, the rule engine's evaluation, evidence provenance |
| GET | `/api/rules`, `/api/rules/{rule_id}` | the legal rules of Arandia |
| POST | `/api/cases/{case_id}/simulate` | start a run → `202` with its ID |
| GET | `/api/runs` | every run this server remembers, newest first |
| GET | `/api/runs/{run_id}` | status, and the full result once finished |
| GET | `/api/runs/{run_id}/events?after=N` | events so far (polling) |
| GET | `/api/runs/{run_id}/stream` | the same events as they happen (SSE) |
| GET | `/api/runs/{run_id}/audit` | the audit report |
| DELETE | `/api/runs/{run_id}` | forget a finished run |

`/docs` is the interactive OpenAPI reference FastAPI generates - a browser is
enough to read a case and start a trial.

### 2. Runs Do Not Block Requests

A trial is minutes of model calls, far longer than an HTTP request should
live. So `POST .../simulate`:

1. checks the case exists and has element bindings (`404` / `409`),
2. builds the provider (`503` if none is configured),
3. starts a background thread, and
4. returns `202` with the run ID and the **effective options**, so the client
   sees exactly what it started.

The client then polls `/events?after=N` or subscribes to `/stream`, and reads
the result from `/runs/{id}` when the status is `completed` or `failed`. The
result is the same `TrialRun` JSON the CLI writes with `--json`.

**Failures never escape the thread.** A run that fails is recorded as
`failed` with the reason (`AdvocateAgentError: No valid prosecution turn ...`),
which the API reports like any other state.

### 3. Streaming (Spec §21)

`/stream` is Server-Sent Events over the `on_event` hook Phase 8 built into
the workflow. Each message's event name is the court event type:

```
event: AGENT_ARGUMENT
data: {"stage": "PROSECUTION_OPENING", "event_type": "AGENT_ARGUMENT", ...}

event: JURY_DECISION
data: {"stage": "JURY_INDEPENDENT_DELIBERATION", ...}

event: run_completed
data: {"run_id": "...", "status": "completed", ...}
```

so a browser can listen for the ones it cares about. The stream reads the
run's own event list from an index rather than a queue, which means **a late
subscriber still gets everything from the beginning**, and `?after=N` resumes
a dropped connection.

Spec §21 allows WebSocket or SSE. SSE fits: the flow is one-way, it is plain
HTTP (no upgrade, no extra proxy configuration), and browsers reconnect on
their own.

### 4. Modes

| `mode` | Runs | Calls |
|---|---|---|
| `court` (default) | the full spec §14 procedure | ~23 |
| `judge` | case → judge → decision | 1 |
| `evidence` | the Evidence Agent's analysis | 1 |

The request body also carries the stage switches (`evidence`,
`cross_examination`, `judge_questions`, `question_rounds`, `jury`, `jurors`,
`deliberation`, `jury_rule`, `audit`, `audit_agent`), `max_attempts`,
`strict_engine_alignment`, and optionally `provider` and `model` - so a client
can run a cheap configuration first. Every field has a default, so an empty
body is a valid request.

### 5. The Provider Is a Dependency

`get_provider_factory` is a FastAPI dependency, not a global. The server
builds providers from its settings; a test overrides the dependency with
scripted agents. That is how **every endpoint, including a full trial, is
tested with no network and no API key**.

### 6. `serve`

```bash
python -m app.cli serve                      # 127.0.0.1:8000
python -m app.cli serve --host 0.0.0.0        # reachable on your network
python -m app.cli serve --port 9000 --reload
```

It binds to `127.0.0.1` by default. The `.env` template's `API_HOST=0.0.0.0`
would expose the server to the whole network, which is not a good default for
a dev tool with API keys in its environment; pass `--host 0.0.0.0` when you
actually want that.

---

## Files

**Created**:
```
backend/app/api/   __init__, app, schemas, runs, dependencies,
                   routers/{__init__, cases, simulations}
backend/tests/test_api/   conftest, test_read_endpoints (10), test_simulations (22)
```

**Modified**:
- `app/cli.py` - the `serve` command
- `backend/requirements.txt` - `fastapi`, `uvicorn`, `pydantic-settings`,
  `httpx`, and `pydantic` moved from 2024 exact pins to ranges matching the
  versions this phase is verified against (FastAPI 0.141, uvicorn 0.53,
  pydantic 2.12)

---

## Tests

```
549 passed ✅ (517 from Phases 1-8, 32 new)
No network access, API keys, or vendor SDKs required.
```

- **Read endpoints**: root and health; `/docs` and the OpenAPI paths; CORS for
  the frontend origin; case list and detail (including the rule evaluation and
  provenance); all 17 rules; 404s
- **Simulations**: a run starts immediately and finishes in the background;
  the result is the whole trial; defaults need no body; `judge` and `evidence`
  modes; runs listed newest first
- **Following a run**: event paging with `after`; the SSE format, names, and
  payloads; `iter_events` yielding live events from a run still in flight and
  stopping when it ends; the audit report; 404 when there is no audit
- **Failures**: a failing run reports why; unknown case; a case without
  bindings; no provider configured; invalid options rejected with `422`
- **Deleting**: forgetting a finished run; `409` while it is still running
- **Provider choice**: the request's provider and model reach the factory, and
  omitting them uses the server default

Beyond the suite, I started the real server with `serve` and checked
`/health`, `/api/cases`, and `/docs` over HTTP.

---

## Not Yet Verified

**No live model call has been made**, as in every phase so far. The API has
only run scripted agents. On the first real run through the API I would watch
that a long trial streams steadily rather than in bursts, and that a dropped
connection resumes correctly with `?after=`.

---

## Known Limitations

1. **Runs live in memory.** Restarting the server forgets them, and only the
   last 50 are kept. Persistence (Postgres, already in the requirements) is a
   later phase; a client can save the result JSON meanwhile.
2. **No cancellation.** A started run cannot be stopped, because the agent
   loop has no interruption point. A cancel flag checked between stages would
   fit naturally in the workflow.
3. **No authentication or rate limiting.** Anyone who can reach the server can
   spend your API budget, which is why it binds to localhost by default. Both
   belong to the production-readiness phase.
4. **One process.** Runs are threads, so throughput is bounded by the
   machine; a task queue would be the next step if that ever matters.
5. **Only CASE_001** can be simulated; the others have no element bindings,
   which the API reports as `409` and `runnable: false`.

---

**Phase 9 Completion Date**: 2026-09-20
**Next Milestone**: Phase 10 - Frontend Visualization
**Overall Progress**: 9/12 phases complete (75%)

**Research Simulation Only**: This system does not provide legal advice or
determine real legal rights or obligations.
