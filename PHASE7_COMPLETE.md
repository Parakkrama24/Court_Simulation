# Phase 7 Implementation Complete ✅

## Overview

**Phase 7: Legal Process Auditor** has been implemented and tested.

**Completion Date**: 2026-09-19
**Status**: ✅ All tests passing (465/465)
**Next Phase**: Phase 8 - Full LangGraph Workflow

```
... → JUDGE_DECISION → LEGAL_PROCESS_AUDIT → CASE_COMPLETE
                              │
              ┌───────────────┴───────────────┐
      deterministic checks            auditor agent
      (always run, in code)     (what code cannot judge)
              └───────────────┬───────────────┘
                        AuditReport
```

The auditor inspects **how the simulation ran**. It never says how the case
should have been decided: a verdict the auditor would not have reached is not
a finding; a verdict reached by a flawed process is.

---

## What Was Built

### 1. Findings and the Report

**Location**: `backend/app/agents/auditor/findings.py`

An `AuditFinding` carries a category (spec §9's four areas plus
hallucinations), a severity, a machine-readable `check`, the agent and stage
responsible, a description, the IDs involved, and its source
(`deterministic` or `auditor_agent`). Findings are filed into the Phase 1
`AuditReport`:

| Category | Report field |
|---|---|
| evidence | `evidence_violations` |
| legal | `legal_violations` |
| procedural | `procedural_violations` |
| reasoning | `reasoning_issues` |
| hallucination | `hallucinations` |

**Overall status** is the worst severity found: `clean`, `minor_issues`,
`major_issues`, `critical_issues`. Info-only findings leave a run clean,
because "this simulation does not implement cross-examination" is a fact about
the system, not a flaw in the run.

### 2. Deterministic Checks

**Location**: `backend/app/workflow/audit.py` - they always run, with or
without a model.

| Spec §9 area | Check | Severity |
|---|---|---|
| Evidence | `caught_hallucination` - an agent cited an invented ID and was rejected | minor |
| Evidence | `accepted_with_invalid_reference` - an accepted output cites something unreal | **critical** |
| Evidence | `unsupported_argument` / `partially_supported_argument` (from EVIDENCE_REVIEW) | minor / info |
| Evidence | Evidence Agent divergences from the engine (witness band, directness, unnamed conflict) | info |
| Legal | `judge_*` - the judge departing from the rule engine | major against the defendant, else info |
| Legal | `defense_rule_other_party` - a defense rule argued for a party it does not concern | minor |
| Reasoning | `assumption_presented_as_fact` - relying on a disputed fact with no assumption listed | minor |
| Reasoning | `one_side_ignored` - the judge or a juror weighed no argument from a party | major |
| Reasoning | `judge_jury_disagreement` | minor (info when hung) |
| Reasoning | `vote_changed_in_deliberation` | info |
| Procedural | `evidence_agent_neutrality` - the neutral analyst used outcome language | major |
| Procedural | `stage_not_implemented` / `stage_skipped` - spec §14 stages that did not occur | info |
| Procedural | `role_violation` - a message sent by an agent with no role at that stage | major |
| Procedural | `repeated_rejections` - an agent needing three or more attempts | info |

Two of these are **defense in depth**: `accepted_with_invalid_reference`
re-validates every citation in every accepted output, and `one_side_ignored`
re-checks a rule the judge and juror validators already enforce. Both should
always be empty; if one ever fires, a validation gate has failed.

### 3. The Auditor Agent

**Location**: `backend/app/agents/auditor/`

It receives a dossier - the record, the arguments, the transcript, the
evidence analysis, the jury decisions, the judgment, and the deterministic
findings - and adds what code cannot judge: self-contradiction across an
agent's turns, misapplied law, partiality. It is told not to repeat the
deterministic findings, and an empty findings list is a valid answer.

It also rates the judge's **decision chain** (spec §23):

```
FACTS → EVIDENCE → LAW → ANALYSIS → DECISION
```

each link `sound`, `weak`, or `broken` with a note. All four links must be
rated exactly once.

**Validation**: a finding naming an agent that did not take part, a stage that
did not occur, or an ID that is not in the trial is rejected and regenerated -
the auditor is held to the same grounding standard as every other agent.

### 4. Auditing Saved Runs

`audit_trial(run, provider=None, ...)` takes any finished `TrialRun`,
including one loaded back from `trial --json` output. Deterministic findings
from a reloaded run are identical to those from the live one (there is a test
for exactly that), so trials can be re-audited later - or audited with a
different model - without paying to re-run them. That is what the evaluation
phase will need.

### 5. Workflow and CLI

| Parameter | Default | |
|---|---|---|
| `audit` | `True` | `False` gives the Phase 6 trial |
| `audit_agent` | `True` | `False` runs deterministic checks only |
| `auditor_provider` | `provider` | a different model for the auditor |

With per-role providers and no shared `provider`, the audit runs
deterministically rather than failing - there is no model to ask.

Events: `AGENT_STARTED`, then `AUDIT_COMPLETED` (spec §21) with the overall
status, severity counts, and whether an agent took part. The report is also a
structured `CourtMessage` of type `audit_report`.

```bash
python -m app.cli trial CASE_001                       # 18 calls, audit included
python -m app.cli trial CASE_001 --deterministic-audit # no auditor model call
python -m app.cli trial CASE_001 --no-audit            # the Phase 6 trial
python -m app.cli trial CASE_001 --json > run.json
python -m app.cli audit run.json                       # re-audit a saved trial
python -m app.cli audit run.json --deterministic-only
```

The transcript ends with the audit: overall status, every finding with its
severity and category, the decision-chain ratings, and the assessment.

---

## Files

**Created**:
```
backend/app/agents/auditor/   __init__, findings, schema, prompts, agent
backend/app/workflow/audit.py
backend/tests/test_agents/test_audit.py (21), test_audit_trial.py (26)
```

**Modified**:
- `app/domain/models.py` - `MessageType.AUDIT_REPORT`
- `app/workflow/adversarial.py` - the audit stage; `TrialRun.audit` and
  `audit_report`; usage includes the auditor
- `app/workflow/__init__.py`, `app/agents/__init__.py` - exports
- `app/cli.py` - `audit` command, `--no-audit`, `--deterministic-audit`,
  audit printing
- `tests/test_agents/test_trial_workflow.py`, `test_evidence_trial.py`,
  `test_jury_trial.py` - pinned to `audit=False`, so they keep guarding the
  Phase 4-6 trials exactly
- `tests/test_agents/conftest.py` - auditor output fixture

---

## Tests

```
465 passed ✅ (418 from Phases 1-6, 47 new)
No network access, API keys, or vendor SDKs required.
```

- **Report**: worst-severity status (including info-only staying clean),
  counts, the deterministic summary, filing by category, the agent's
  assessment taking precedence
- **Auditor validation**: unknown agent, stage, and reference; empty agent and
  stage allowed; every chain link rated exactly once; the finding limit
- **Auditor agent**: the neutral prompt, dossier and deterministic findings in
  the prompt, regeneration on a bad reference, giving up
- **Deterministic checks**: each check above, staged by running a real trial
  and changing one thing - a fabricated citation, an invalid ID slipped into
  an accepted argument, an unsupported argument, a neutrality breach, a
  conviction beyond the engine, `LAW_201` argued for the defendant, a missing
  assumption, a side ignored, a jury disagreement, a forged message sender,
  repeated rejections
- **Audit stage**: it closes the trial before `CASE_COMPLETE`; the message and
  event; deterministic-only mode; a separate auditor model; per-role providers
  auditing without a model; a saved run auditing identically
- **CLI**: the audit transcript, `--deterministic-audit`, auditing a saved run
  with and without a model, and an unreadable file

---

## Not Yet Verified

**No live model call has been made.** On the first real runs I would watch:

- whether the auditor finds anything real, or mostly restates the
  deterministic findings despite being told not to
- whether it stays inside its remit or starts re-deciding the case
- how often the decision chain comes back anything but `sound` - a rubber-stamp
  auditor would be worth knowing about early
- the cost of one extra call on a large dossier

---

## Known Limitations

1. **Self-contradiction detection is the agent's job alone.** Comparing an
   agent's claims across turns deterministically would need semantic
   comparison; the auditor agent is the only check on it.
2. **Neutrality is still keyword-based** on the deterministic side.
3. **The audit reports; it does not gate.** Nothing fails a run because the
   audit found major issues. A `--fail-on` threshold would be a small
   addition once the evaluation phase defines what should block.
4. **Cross-examination and judge questions** remain unimplemented - now
   reported honestly by the auditor as `stage_not_implemented` rather than
   passing silently.

---

**Phase 7 Completion Date**: 2026-09-19
**Next Milestone**: Phase 8 - Full LangGraph Workflow
**Overall Progress**: 7/12 phases complete (58%)

**Research Simulation Only**: This system does not provide legal advice or
determine real legal rights or obligations.
