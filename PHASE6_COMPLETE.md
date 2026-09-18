# Phase 6 Implementation Complete ✅

## Overview

**Phase 6: Jury** has been implemented and tested.

**Completion Date**: 2026-09-18
**Status**: ✅ All tests passing (418/418)
**Next Phase**: Phase 7 - Legal Process Auditor

```
... → CLOSING_ARGUMENTS
    → JURY_INDEPENDENT_DELIBERATION   jury_1, jury_2, jury_3 decide alone
    → JURY_DELIBERATION (optional)    each reconsiders once, seeing the panel
    → verdict engine                  deterministic tally
    → JUDGE_DECISION                  sees the jury's result; agreement recorded
```

---

## What Was Built

### 1. Juror Agents

**Location**: `backend/app/agents/jury/`

Each juror decides every charge and returns what spec §8 asks for:

| Spec §8 | Field |
|---|---|
| verdict | `charge_verdicts[].verdict` - guilty / not guilty, per charge |
| reasoning | `charge_verdicts[].reasoning` and overall `reasoning` |
| evidence relied upon | `charge_verdicts[].fact_ids / evidence_ids / witness_ids` |
| legal rules relied upon | `charge_verdicts[].rule_ids` |
| uncertainties | `uncertainties` |
| confidence | per charge and overall |

Jurors also list the arguments they weighed. Each decision maps onto the domain
`Verdict` (`jury_1` … `jury_N`, independent and deliberation rounds), giving
the `jury_decisions` list that spec §17 asks the court state to hold.

### 2. Independence Is Structural

> "Do not allow jury members to see other jury decisions before producing
> their initial decision." - spec §8

A juror's independent request is built by a function that takes the trial
record and nothing else, so there is no parameter through which another
juror's view could enter. The test suite proves it: the three independent
prompts are **byte-identical** and contain no juror IDs.

### 3. Controlled Deliberation

One optional structured round, not free-form chat. Each juror receives a
`<jury_room>` with every juror's independent decision (its own marked
`"you": true`) and gives a final verdict plus `response_to_panel`. The prompt
says to change a verdict only when the record persuades you, not because of
how many jurors voted which way. Validation enforces this: **a changed vote
must cite at least one fact, evidence item, or witness**, or it is rejected.
With a single juror there is no one to deliberate with, so the round is
skipped.

### 4. The Verdict Engine

**Location**: `backend/app/agents/jury/aggregation.py`

The architecture diagram's "Verdict Engine" - code, not a model:

| Rule | Guilty | Not guilty | Otherwise |
|---|---|---|---|
| `unanimous` (default) | every juror | every juror | **hung** |
| `majority` | more than half | more than half | **hung** (a tie) |

Per charge it reports the votes, the outcome, whether the panel was unanimous,
and **agreement**, the share of jurors on the larger side. It does this before
and after deliberation, and lists every vote that changed. That is spec §23's
"verdict agreement: how often do independent jury members agree?", computed
from the independent round, which is the only round where jurors really are
independent.

### 5. Juror Validation

| Rejected (regenerate) | Why |
|---|---|
| fact / evidence / witness / rule / argument ID not in the record | hallucination |
| a charge undecided, decided twice, or invented | incomplete |
| a charge verdict relying on no offense rule | a charge is decided under a law |
| a guilty verdict citing nothing from the record | P003 |
| a party's arguments ignored entirely | weigh both sides |
| a changed vote in deliberation citing nothing from the record | no flipping to follow the majority |

A **not-guilty** verdict may cite nothing: it can rest on the absence of proof
(P002).

### 6. Judge and Jury

- The judge (`judge.v4`) sees the jury's tallied result under `jury`. It is told
  to give the verdict real weight, to decide on the record, and to explain any
  departure with cited evidence.
- **Only the judge sees the jury.** The advocates never do.
- The judge's decision is compared with the jury's final verdict, charge by
  charge. The comparison is recorded in `TrialRun.judge_jury_agreement` and in
  the `JUDGE_DECISION` event, and printed in the transcript.

### 7. Workflow and CLI

`run_adversarial_trial(...)` gains:

| Parameter | Default | |
|---|---|---|
| `jury` | `True` | `False` gives the Phase 5 trial |
| `jurors` | `3` | 1-12 |
| `deliberation` | `True` | one controlled round |
| `jury_rule` | `UNANIMOUS` | or `MAJORITY` |
| `juror_providers` | `provider` for all | a different model per juror |
| `juror_perspectives` | none | optional background per juror, for research configs |

Events: `JURY_DECISION` (spec §21) per juror per round, with the changed
charges in deliberation, then `JURY_VERDICT` with outcomes, agreement before
and after, and the number of vote changes.

```bash
python -m app.cli trial CASE_001                  # 17 calls
python -m app.cli trial CASE_001 --quick          # 12 calls
python -m app.cli trial CASE_001 --no-jury        # the Phase 5 trial
python -m app.cli trial CASE_001 --jurors 5 --jury-rule majority --no-deliberation
```

The transcript shows each juror's verdicts with citations and uncertainties,
marks changed votes, then prints the tally, agreement before → after, and
whether the judge agreed with the jury on each charge.

---

## Design Choices Worth Knowing

1. **Identical instructions by default.** Nothing in the spec asks for juror
   personas, and invented backgrounds would bias the result. With identical
   prompts, variation between jurors comes only from the model itself. That
   variation may be small, so high agreement is partly by construction.
   `juror_providers` (different models) and `juror_perspectives` are there to
   vary this deliberately; the perspective is stored on each verdict.
2. **The judge decides; the jury informs.** The spec places `JUDGE_DECISION`
   after the jury and asks the judge for a reasoned decision, but doesn't say
   the jury's verdict binds. I kept the judge's decision authoritative and made
   every judge-jury disagreement visible rather than impossible. If you want the
   jury to bind, that's a small rule to add.
3. **Unanimity by default** means a single dissenting juror hangs the jury on
   that charge. This is the conventional criminal standard, and the fictional
   jurisdiction doesn't specify one.

---

## Files

**Created**:
```
backend/app/agents/jury/   __init__, schema, aggregation, validation, prompts, agent
backend/tests/test_agents/test_jury.py (34), test_jury_trial.py (22)
```

**Modified**:
- `app/domain/models.py` - `MessageType.JURY_VERDICT`
- `app/agents/record.py` - optional `jury` section
- `app/agents/judge/` - `judge.v4`, accepts `jury_context`
- `app/workflow/adversarial.py` - jury stages, verdict engine, judge-jury
  agreement, usage includes jurors
- `app/cli.py` - `--no-jury`, `--jurors`, `--no-deliberation`, `--jury-rule`,
  jury transcript
- `tests/test_agents/test_trial_workflow.py`, `test_evidence_trial.py` - pinned
  to `jury=False`, so they keep guarding the Phase 4 and 5 trials exactly
- `tests/test_agents/conftest.py` - juror verdict fixture

---

## Tests

```
418 passed ✅ (362 from Phases 1-5, 56 new)
No network access, API keys, or vendor SDKs required.
```

- **Verdict engine**: unanimous acquittal and conviction, a split hanging a
  unanimous jury, majority rule, a majority tie, agreement before and after
  deliberation, vote changes, judge-jury agreement including a hung charge
- **Validation**: every rejection rule, and the two allowances (not guilty
  without citations; an unchanged vote without new citations)
- **Agent**: system prompt and perspectives, no jury room in the independent
  request, the whole panel in the deliberation request, verdict and message
  mapping, changed charges, regeneration, giving up
- **Trial**: byte-identical independent prompts; a juror persuaded in
  deliberation turning a hung charge into a unanimous acquittal; the judge sees
  the jury and the advocates don't; event order from closing → jury →
  deliberation → verdict → judge; no deliberation; a single juror; majority rule
  with perspectives and a recorded judge-jury disagreement; a shared provider;
  bad configurations rejected before any model call
- **CLI**: the jury transcript, and custom jury options

---

## Not Yet Verified

**No live model call has been made.** What I'd look at on the first real runs:

- **Independent agreement**: with identical instructions, do the three jurors
  ever disagree on CASE_001? If they never do, the agreement metric needs
  `juror_providers` or perspectives to mean much.
- **Deliberation**: do jurors change votes, and do the changes follow the
  record or the majority?
- **Judge vs jury**: how often does the judge depart from a unanimous jury?
- **Cost**: the full trial is now 17 calls, the interaction log records exact
  tokens, and `--no-deliberation` saves three.

---

## Known Limitations

1. **Deliberation is one round.** Real juries iterate. More rounds are an easy
   extension, but each adds a call per juror.
2. **Jurors run sequentially.** Their independent calls could run in parallel,
   and nothing in the design prevents it; that's a latency improvement for when
   it matters.
3. **Cross-examination and judge questions** are still not implemented.
4. **Only CASE_001** is runnable end to end.

---

**Phase 6 Completion Date**: 2026-09-18
**Next Milestone**: Phase 7 - Legal Process Auditor
**Overall Progress**: 6/12 phases complete (50%)

**Research Simulation Only**: This system does not provide legal advice or
determine real legal rights or obligations.
