# Phase 8 Implementation Complete ✅

## Overview

**Phase 8: Full LangGraph Workflow** has been implemented and tested.

**Completion Date**: 2026-09-19
**Status**: ✅ All tests passing (517/517)
**Next Phase**: Phase 9 - FastAPI Backend

The whole spec §14 procedure now runs as a LangGraph state machine. The two
stages the auditor had been reporting as `stage_not_implemented` -
**CROSS_EXAMINATION** and **JUDGE_QUESTIONS** - are built, and the spec's one
named conditional transition works:

> "The Judge should be able to request additional analysis if an argument
> lacks evidence." - spec §14

```bash
cd backend
python -m app.cli court CASE_001 --show-graph   # the state machine (Mermaid), no model call
python -m app.cli court CASE_001 --events       # run it, one line per event, live
```

---

## What Was Built

### 1. The State Machine

**Location**: `backend/app/workflow/graph.py`

A `StateGraph` over a typed `CourtState` with 20 nodes, including the answer
and answer-review nodes of the questioning loop. Every spec §17 field is in
the state, and the tests check each one on a finished run:

| Spec §17 field | Holds |
|---|---|
| `case`, `facts`, `evidence` | the case record |
| `applicable_laws` | the `LegalRule` objects, not just IDs |
| `current_stage` | the stage last completed (`CASE_COMPLETE` at the end) |
| `prosecution_arguments`, `defense_arguments` | every argument, by side |
| `evidence_analysis` | the Evidence Agent's analysis |
| `judge_questions` | every question the judge put |
| `jury_decisions` | every juror's `Verdict`, both rounds |
| `judge_decision` | the judge's `Verdict` |
| `audit_report` | the `AuditReport` |
| `event_history` | every event, in order |

Append-only fields use `operator.add` reducers, so each node returns only what
it adds - the idiomatic LangGraph shape.

**Conditional transitions** decide every branch:

| After | Next | When |
|---|---|---|
| CASE_INITIALIZATION | EVIDENCE_ANALYSIS or PROSECUTION_OPENING | Evidence Agent on / off |
| DEFENSE_ARGUMENT | CROSS_EXAMINATION, EVIDENCE_REVIEW, or PROSECUTION_REBUTTAL | cross-examination on; else evidence on |
| EVIDENCE_REVIEW | **JUDGE_QUESTIONS** or PROSECUTION_REBUTTAL | an argument is unsupported, rounds remain |
| review of answers | **JUDGE_QUESTIONS** again or PROSECUTION_REBUTTAL | an answer is still unsupported, rounds remain |
| CLOSING_ARGUMENTS | JURY_INDEPENDENT_DELIBERATION or JUDGE_DECISION | jury on / off |
| JURY_INDEPENDENT_DELIBERATION | JURY_DELIBERATION or verdict engine | 2+ jurors, deliberation on |
| JUDGE_DECISION | LEGAL_PROCESS_AUDIT or CASE_COMPLETE | audit on / off |

The judge-questions loop is a real cycle in the graph, bounded by
`max_question_rounds` (default 1). LangGraph's default recursion limit (25
steps) is too tight for the full procedure plus question rounds, so it is set
to 200.

### 2. JUDGE_QUESTIONS: Requesting More When an Argument Lacks Evidence

**Location**: `backend/app/agents/judge/questions.py`

1. `EVIDENCE_REVIEW` finds an argument `unsupported` by what it cites.
2. **The judge questions the party that made it.** This uses a separate,
   neutral prompt - "questions, not a decision" - because the decision prompt
   tells the judge to decide every charge. Validation: every flagged argument
   must be covered, each question must go to the party that made the argument,
   and there are at most 6 questions. Questions get court IDs (`JQ1-1`).
3. **The party answers** (`AGENT_RESPONSE`, spec §21). Every question must be
   answered by putting its ID in `responds_to`, citing the record. The prompt
   invites narrowing or withdrawing a claim the record doesn't support -
   "conceding a gap is better than repeating it". A party cannot answer the
   other side's question.
4. **The Evidence Agent reviews the answers.**
5. If an answer is still unsupported and rounds remain, the loop repeats.

From then on, every later speaker's record includes the questions: advocates,
the reviewer of the answers, jurors, and the judge. The jurors' independent
prompts stay byte-identical.

### 3. CROSS_EXAMINATION

Each side, prosecution then defense, tests the testimony the other relies on:
contradictions, missing corroboration, and the E003 grounds. **Every argument
must name the witness it examines**, or the turn is rejected. Cross-examination
is also available to the linear `trial` runner.

This is cross-examination as structured challenge to recorded testimony. There
are no witness agents answering live questions - see the limitations below.

### 4. One Set of Steps, Two Runners

**Location**: `backend/app/workflow/steps.py`

Every stage is one function that returns what it produced plus the events and
messages to record; it never mutates trial state. `open_court` checks the
whole configuration and seats the agents before any model is called. Both
runners use these steps:

- **`run_court`** (graph) - the full procedure
- **`run_adversarial_trial`** (linear) - custom stage plans, repeated stages,
  and the Phase 4-7 trials exactly

The linear runner was rewritten onto the shared steps with **no behaviour
change**: all 467 existing tests passed unmodified through the refactor.
`TrialRun` moved to its own module (`run.py`), which also removed an
import-cycle workaround in the audit.

### 5. Recording What Did Not Run

A stage that does not run is recorded as a `STAGE_SKIPPED` event with a
reason:

- "the evidence review found no argument unsupported"
- "disabled in this run's configuration"
- "a single juror has no one to deliberate with"
- "... the Evidence Agent is disabled"

The audit turns these into precise `stage_not_required` findings. A stage
missing with no recorded reason - a linear stage plan that leaves it out - is
still `stage_skipped`.

### 6. Live Events and the CLI

`run_court(..., on_event=callback)` calls the callback with every event as
each node completes, using LangGraph's streaming. The tests check that the
stream equals the final `event_history`, exactly and in order. This is the
hook Phase 9's streaming will build on.

```bash
python -m app.cli court CASE_001                        # full procedure, transcript at the end
python -m app.cli court CASE_001 --events               # live, one line per event
python -m app.cli court CASE_001 --show-graph           # Mermaid, no model call
python -m app.cli court CASE_001 --question-rounds 2    # allow a second round
python -m app.cli court CASE_001 --no-cross-examination --no-judge-questions
python -m app.cli trial CASE_001                        # custom plans still work
```

The transcript shows cross-examination turns, the judge's questions (what was
flagged, who was asked what), and the answers (`answers JQ1-1`) where they
happened.

---

## Bugs the New Tests Caught

1. **A false critical finding.** The audit's re-check of accepted citations
   rejected answers that cite `JQ1-1`, because it only knew argument IDs. That
   check should never fire on a sound run, so it would have made every
   questioned trial look untrustworthy. Question IDs are now known references.
2. **Questions missing from later records.** After questioning, the rebuttals,
   jurors, and judge saw answers citing `JQ1-1` without the question itself.
   The questions now reach every later speaker.

---

## Files

**Created**:
```
backend/app/agents/judge/questions.py
backend/app/workflow/graph.py, steps.py, run.py
backend/tests/test_agents/test_judge_questions.py (22), test_court_graph.py (28)
```

**Modified**:
- `app/domain/models.py` - `JudgeQuestion`; message types
  `cross_examination`, `judge_question`, `answer`
- `app/agents/advocate/` - cross-examination stage and rule; answering the
  judge (`answer()`, question-aware `responds_to` validation); `advocate.v3`
- `app/agents/judge/` - `ask_questions`
- `app/agents/record.py` - `judge_questions` in the shared record
- `app/agents/evidence/`, `jury/`, `judge/` - pass the questions into their records
- `app/workflow/adversarial.py` - rewritten onto the shared steps
- `app/workflow/audit.py` - `stage_not_required`; question rounds audited; the
  judge and parties may speak at `JUDGE_QUESTIONS`; the false-positive fix
- `app/cli.py` - `court` command; transcript and live event printing
- `backend/requirements.txt` - `langgraph>=1.2,<2`. The old `langgraph==0.2.45`
  and `langchain==0.3.*` pins conflict with LangGraph 1.x, and nothing imports
  LangChain directly, so they are removed.
- 3 audit tests updated: cross-examination and judge questions are no longer
  "not implemented"

---

## Tests

```
517 passed ✅ (467 from Phases 1-7, 50 new)
No network access, API keys, or vendor SDKs required.
```

- **Full procedure**: the exact spec §14 stage order; every stage ran;
  cross-examination turns; the judge questioning a flagged argument; the answer
  and its review; later speakers, jurors, and the judge seeing the questions;
  an accurate audit; events streamed once and in order; 23 logged calls; the
  run serialising and re-auditing identically
- **State**: every spec §17 field on a finished `CourtState`
- **Transitions**: no questions when nothing is unsupported, with the recorded
  reason; a second round when answers stay unsupported; stopping at the round
  limit; questions off; cross-examination off; the Evidence Agent off; jury and
  audit off; a single juror; a deterministic audit
- **Configuration**: errors raised before any model call; seating the agents;
  cross-examination in the linear runner
- **Questions and answers**: every validation rule, IDs, the separate prompt,
  regeneration, answers by ID, cross-party answers rejected
- **CLI**: `--show-graph`, the transcript with questions and answers, and
  `--events`

---

## Not Yet Verified

**No live model call has been made**, as before. The full procedure is now
**23+ calls** per trial: evidence analysis, 8 openings and arguments, 2
cross-examination turns, the review, questions and answers and their review,
4 rebuttals and closings, 6 jury calls, the judge, and the auditor.
`--no-cross-examination`, `--no-judge-questions`, `--no-deliberation`, and
`--deterministic-audit` each trim calls. On the first real runs I would watch:

- how often the review flags arguments, i.e. how often the questioning loop runs
- whether parties narrow or withdraw claims when questioned, or restate them
- whether cross-examination stays on testimony or drifts into re-arguing

---

## Known Limitations

1. **No witness agents.** Cross-examination challenges recorded testimony; it
   does not question a live witness. Witness agents would be a natural
   extension.
2. **The judge questions only when the Evidence Agent flags something.** The
   judge cannot yet decide by itself that it wants to ask. That would need an
   extra judge call on every trial.
3. **No checkpointing.** A failed agent stops the run; it cannot resume
   mid-trial. LangGraph checkpointers would add that when the API phase needs
   long-running trials.
4. **Sequential execution.** Jurors could run in parallel as a LangGraph
   fan-out; not needed yet.
5. **Only CASE_001** has seeded element bindings, so it remains the only case
   runnable end to end.

---

**Phase 8 Completion Date**: 2026-09-19
**Next Milestone**: Phase 9 - FastAPI Backend
**Overall Progress**: 8/12 phases complete (67%)

**Research Simulation Only**: This system does not provide legal advice or
determine real legal rights or obligations.
