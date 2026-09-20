# Phase 10 Implementation Complete ✅

## Overview

**Phase 10: Frontend Visualization** has been implemented and tested.

**Completion Date**: 2026-09-20
**Status**: ✅ All tests passing (backend 549/549, frontend 60/60)
**Next Phase**: Phase 11 - Evaluation Framework

The simulation now has a face: a courtroom you can watch while it runs.

```bash
# terminal 1 - the API
cd backend && python -m app.cli serve

# terminal 2 - the dashboard
cd frontend && npm install && npm run dev      # http://localhost:3000
```

---

## What Was Built

### 1. The Pages

| Route | |
|---|---|
| `/` | **Case selection**: every seeded case, whether it can be simulated, and the runs so far |
| `/cases/{case_id}` | **Case details**: facts, evidence, witnesses, laws, and what the rule engine computed - plus the form that starts a trial |
| `/runs/{run_id}` | **The live courtroom**: the bench, the timeline, the event feed, and every panel |
| `/runs` | Every run the server remembers |
| `/rules` | The 17 legal rules of Arandia |

### 2. The Courtroom (Spec §20)

The main screen is the layout the spec draws: prosecution, judge, and defense
across the bench, with the evidence analyst, the jury, and the auditor below,
and the timeline of the procedure beside them.

A seat lights up while that agent is working. That is not an animation on a
timer: the backend emits `AGENT_STARTED` when an agent begins and a finishing
event when it returns, so the dashboard shows exactly who the simulation is
waiting on.

### 3. The Panels (Spec §20)

| Panel | Shows |
|---|---|
| **Evidence** | Every exhibit with its reliability and chain of custody, and the Evidence Agent's claims, contradictions, and what the record is missing |
| **Legal rules** | The laws the agents cited and who cited them, then what the rule engine computed element by element, then the rest of the statute book |
| **Debate** | Prosecution and defense arguments in the order the court heard them, each with what it cites, its confidence, and whether the evidence review found it supported - with the judge's questions in the place they were asked |
| **Jury** | The tally per charge, each juror's verdict independently and after deliberation, and every vote that changed |
| **Judge decision** | Findings of fact, applicable law, reasoning element by element, and the verdict - kept apart, as spec §7 requires - and whether the judge agreed with the jury |
| **Audit** | The overall status, the decision chain, and every finding grouped as hallucinations, evidence violations, procedural violations, legal violations, and reasoning issues |

### 4. Live, Then Complete

A trial is minutes of model calls, so the dashboard shows two different
things and never confuses them:

- **While it runs**, everything comes from the event stream, because that is
  all the backend has published. The feed reports what was presented,
  reviewed, asked, and decided; the debate tab lists the arguments by ID and
  marks the ones the evidence review rejected.
- **Once it ends**, the dashboard reads `/api/runs/{id}` and renders the full
  result in the panels.

A panel with nothing to show says so. It never fills the gap with a
placeholder - the same rule the agents work under.

### 5. Streaming (Spec §21)

`useRunStream` subscribes to `/api/runs/{id}/stream` with `EventSource`,
listening for each court event type **by name** - `AGENT_ARGUMENT`,
`JUDGE_QUESTION`, `JURY_DECISION`, `AUDIT_COMPLETED`, and the rest - because
that is how the backend names its messages.

If the browser cannot keep the stream open, the hook falls back to polling
`/api/runs/{id}/events?after=N`. The backend numbers events and a stream
always replays a run from its first event, so a reconnect - or React's
double-mount in development - loses and repeats nothing.

### 6. Typed Against the API

`src/lib/types.ts` is the backend's contract in TypeScript: every schema in
`app/api/schemas.py` and every domain model they serialise. The client
(`src/lib/api.ts`) returns those types, so a panel that reads a field the
backend does not send fails at build time rather than in front of a user.

Errors carry the backend's own `detail`. When the API is simply not running,
the page says so and prints the command that starts it.

---

## Files

**Created**: `frontend/`

```
src/app/         layout, globals.css, page (cases), cases/[caseId],
                 runs, runs/[runId], rules
src/components/  SiteHeader, Courtroom, Timeline, LiveFeed, CaseRecord,
                 SimulationForm, RunRow, Tabs, Problem, ui
src/components/panels/  Evidence, Rules, Debate, Jury, JudgeDecision, Audit
src/hooks/       useRunStream (SSE + polling), useApi
src/lib/         api, types, court, runState, result
package.json, tsconfig.json, next.config.mjs, postcss.config.mjs,
vitest.config.mts, README.md, .env.local.example
```

**Modified**: `README.md`, `ARCHITECTURE.md`, `QUICKSTART.md`, `.gitignore`

---

## Tests

```
frontend   60 passed ✅   (vitest, ~5s, no backend needed)
backend   549 passed ✅   (unchanged)
tsc --noEmit  clean       next build    clean
```

The panels are rendered from **a real finished run**: a full court procedure
produced by `run_court` with the backend's own scripted agents, serialised
exactly as the API
returns it and kept as `src/lib/__fixtures__/trial-run.json`.

- **The courtroom vocabulary** (14): the label for every agent and stage, the
  seat a stage belongs to, and the line the feed writes for each event type -
  arguments, answers, the analysis, the review, questions, votes, the tally,
  the judgment, the audit, a skipped stage, and an event it has never seen
- **What the UI derives from events** (16): every argument in order, what the
  review rejected, the judge's questions, both jury rounds, the tally and the
  judgment; the stage running now and the agent working; stages still pending;
  nobody left working once a run stops; a run with no events; a skipped stage;
  and reading the result of each of the three modes
- **The panels** (16): both sides and what they cite, the unsupported argument
  marked, the judge's question in its place; the analyst's claims and the
  record; the tally, the rule, and each juror; findings, law, reasoning and
  verdict kept apart, and whether judge and jury agreed; every audit category
  with a finding's source; which laws the agents cited - and what each panel
  says when it has nothing to show
- **The client** (9): the URL it calls, the body it posts, IDs escaped in the
  path, event paging, the backend's `detail` carried on an error, and the
  instruction to start the backend when it is not answering
- **Following a run** (5): the stream opens, its named events collect, the run
  is re-read when it completes, the polling fallback resumes at the right
  index when the stream breaks, and a run that cannot be read reports why

### Beyond the suite

The dashboard was built, started (`next start`), and checked against the real
API: every route answered `200`, the page carried the spec §24 disclaimer, and
the backend accepted the browser origin through CORS.

Then a **full 23-call trial was run through the real HTTP API** - the backend
pointed at a stub OpenAI-compatible server replaying the scripted court -
and:

- the stream emitted **51 events**, every one of them a message name the
  dashboard's `EventSource` subscribes to;
- the finished run's JSON matched the fixture the panels are typed against,
  key for key, including `judgment.decision`, `evidence_analysis.output`,
  `jury_result`, `audit.report`, a turn, and a juror's decision.

---

## Not Yet Verified

**No live model call has been made**, as in every phase so far: the trial the
dashboard was checked against came from a scripted stub, not a model.

**No browser session was driven.** Rendering is covered by component tests in
jsdom and the pages were fetched over HTTP, but nothing here clicked through
the UI or watched a stream arrive in a real browser. On the first real run I
would watch that a long trial updates steadily rather than in bursts, and that
pulling the network mid-trial visibly falls back to polling.

---

## Known Limitations

1. **Nothing is persisted.** Runs live in the server's memory, so restarting
   the backend empties the run list. That is a backend limitation the UI
   inherits.
2. **A run cannot be cancelled** from the dashboard, because the backend has
   no way to stop one.
3. **Only CASE_001 can be simulated.** The others have no element bindings;
   the case list marks them "record only".
4. **No authentication.** The dashboard is a local research tool, and the
   backend binds to localhost by default.

---

**Phase 10 Completion Date**: 2026-09-20
**Next Milestone**: Phase 11 - Evaluation Framework
**Overall Progress**: 10/12 phases complete (83%)

**Research Simulation Only**: This system does not provide legal advice or
determine real legal rights or obligations.
