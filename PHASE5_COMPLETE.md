# Phase 5 Implementation Complete ✅

## Overview

**Phase 5: Evidence Agent** has been implemented and tested.

**Completion Date**: 2026-09-18
**Status**: ✅ All tests passing (362/362)
**Next Phase**: Phase 6 - Jury (three independent jury agents)

The trial now follows spec §14 up to the jury:

```
CASE_INITIALIZATION → RULE_EVALUATION
→ EVIDENCE_ANALYSIS                              ◄ new: neutral analysis of the record
→ PROSECUTION_OPENING → DEFENSE_OPENING
→ PROSECUTION_ARGUMENT → DEFENSE_ARGUMENT
→ EVIDENCE_REVIEW                                ◄ new: every argument checked
→ PROSECUTION_REBUTTAL → DEFENSE_REBUTTAL
→ CLOSING_ARGUMENTS → JUDGE_DECISION → CASE_COMPLETE
```

---

## What Was Built

### 1. The Evidence Agent

**Location**: `backend/app/agents/evidence/`

A neutral analyst working for the court. Its system prompt forbids advocating
for either side and forbids saying whether anyone should be convicted or
acquitted, and its output schemas have no field where an outcome could go.

**Spec §6 responsibilities, and where each lives:**

| Responsibility | Implemented as |
|---|---|
| Analyze evidence | `evidence[]` - every item exactly once, with the facts it bears on and reliability concerns |
| Which claims are directly supported | `claims[]` - status, supporting / contradicting evidence and witnesses, confidence, reasoning |
| Identify circumstantial evidence | `evidence[].directness` - direct or circumstantial (rules E001 / E002) |
| Identify contradictions | `contradictions[]` - the conflicting items and why it matters (E004 / P005) |
| Witness reliability by predefined rules | `witnesses[]` - rated high / moderate / low on the E003 grounds, checked against the engine's deterministic E003 score |
| Detect unsupported claims | claims with status `unsupported`, **and** `EVIDENCE_REVIEW` of every argument |
| Identify missing evidence | `missing_evidence[]` - tied to the legal elements (rule + condition) it bears on |
| Track evidence provenance | **computed in code** from the record - see below |

**Claim status**, as spec §6 requires, is `established` / `disputed` /
`unsupported`, and it must agree with the claim's own citations:

| Status | Support | Contradiction |
|---|---|---|
| established | at least one | none |
| disputed | at least one | at least one |
| unsupported | none | - |

(Spec §6's example uses `"status": "supported"`, but its field list says
established / disputed / unsupported; I followed the list.)

### 2. Provenance Is Computed, Not Generated

**Location**: `backend/app/agents/evidence/provenance.py`

Where evidence came from is a fact about the record, so it is traced in code:
source, who handled it, when, which witness it came from, which facts it
supports or contradicts, its recorded reliability, and the **gaps** - what the
record doesn't say. For CASE_001 this surfaces two real gaps:

- **E005** (911 recording): no record of who retrieved it
- **E006** (neighbour's testimony): no date recorded

The model receives provenance as input and is told not to invent
chain-of-custody details.

### 3. Evidence Review of Arguments

After `DEFENSE_ARGUMENT` - where spec §14 places `EVIDENCE_REVIEW` - the agent
reviews every argument presented so far and grades each one `supported`,
`partially_supported`, or `unsupported`, listing specific issues: overclaiming,
citations that contradict the claim, disputed facts presented as settled,
assumptions presented as facts. If the plan includes a second review, it
covers only arguments made since the first.

### 4. Validation

| Rejected (regenerate) | |
|---|---|
| any fact / evidence / witness / legal-element ID not in the record | hallucination |
| a status that contradicts the claim's own citations | incoherent |
| an item listed as both supporting and contradicting a claim | incoherent |
| an evidence item or witness not assessed, or assessed twice | incomplete |
| a disputed fact (F004 in CASE_001) that no claim covers | P005 |
| a contradiction naming fewer than two items | not a contradiction |
| an argument left unreviewed, reviewed twice, or not under review | incomplete |
| a review below `supported` that lists no issues | unexplained |

| Flagged (recorded for the auditor) | |
|---|---|
| outcome language: guilty, convict, acquit, innocent | neutrality - a keyword heuristic, so flagged, not rejected |
| witness rated outside the band of the engine's E003 score | engine divergence |
| circumstantial-type evidence assessed as direct | engine divergence |
| a fact conflict the engine found that no contradiction names | engine divergence |

### 5. Everyone Sees the Evidence Work

The analysis and all reviews so far are added to the shared record under
`evidence_analysis` - with `argument_reviews` - for every later speaker:

- **Advocates** (`advocate.v2`): may rely on or contest it with evidence, and
  are told to answer a weakness it finds rather than repeat the argument
- **Judge** (`judge.v3`): it informs findings but doesn't replace them; reviews
  show where an argument's citations fall short
- **The Evidence Agent's own review** sees its earlier analysis, so the two stay
  consistent

The data is passed as plain dicts (`evidence_context`), so agents don't import
one another.

### 6. Workflow and CLI

- `run_adversarial_trial(..., evidence=True, evidence_provider=...)` - the
  analyst can run on its own model. `evidence=False` gives exactly the Phase 4
  trial.
- `check_stages` now rejects: a review with the Evidence Agent disabled, a
  review before any argument, and two reviews with nothing new between them.
- Events: `EVIDENCE_ANALYZED` (spec §21) with claim counts by status, and
  `EVIDENCE_REVIEWED` with which arguments were reviewed and which were
  unsupported.
- `run_evidence_analysis` - the analysis alone (one call).

```bash
python -m app.cli evidence CASE_001 --show-prompt   # no API call
python -m app.cli evidence CASE_001                 # 1 call
python -m app.cli trial CASE_001 --quick            # 6 calls: analysis, 4 turns, judge
python -m app.cli trial CASE_001                    # 11 calls: + evidence review
python -m app.cli trial CASE_001 --no-evidence      # the Phase 4 trial, 9 calls
```

The trial transcript prints the analysis first, then each review where it
happened in the debate.

---

## Files

**Created**:
```
backend/app/agents/evidence/   __init__, provenance, schema, prompts, validation, agent
backend/app/workflow/evidence_only.py
backend/tests/test_agents/test_evidence_agent.py (46), test_evidence_trial.py (25)
```

**Modified**:
- `app/domain/models.py` - `MessageType.EVIDENCE_ANALYSIS`, `EVIDENCE_REVIEW`
- `app/agents/record.py` - optional `evidence_analysis` section
- `app/agents/advocate/` - `advocate.v2`, accepts `evidence_context`
- `app/agents/judge/` - `judge.v3`, accepts `evidence_context`
- `app/workflow/adversarial.py` - evidence stages, per-role evidence provider,
  new stage-plan rules, usage includes the analyst
- `app/cli.py` - `evidence` command, `trial --no-evidence`, evidence printing
- `tests/test_agents/test_trial_workflow.py` - pinned to `evidence=False`, so
  those 23 tests keep guarding the Phase 4 trial exactly
- `tests/test_agents/conftest.py` - analysis and review fixtures

---

## Tests

```
362 passed ✅ (291 from Phases 1-4, 71 new)
No network access, API keys, or vendor SDKs required.
```

- **Provenance**: every item traced; handler, date, and facts; testimonial
  evidence linked to its witness; the E005 and E006 gaps; unlinked evidence
- **Analysis validation**: each rejection rule; each flag; reliability bands
- **Review validation**: completeness, unknown and duplicate reviews,
  unexplained weak findings, the neutrality flag
- **Agent**: the neutral prompt, provenance and disputed facts in the prompt,
  claim counts in the message, regeneration on an incoherent status, giving up
- **Trial**: analysis before any argument; review exactly between
  `DEFENSE_ARGUMENT` and `PROSECUTION_REBUTTAL` covering all 8 arguments;
  advocates see the analysis from the start and reviews only after the review;
  the review sees its own analysis; the judge sees both; 11 messages and 11
  logged calls; quick trials analyse but don't review; a second review covers
  only new arguments; `evidence=False` removes the agent entirely
- **CLI**: `evidence --show-prompt`, the `evidence` transcript, the trial
  printing the analysis before the opening

---

## Not Yet Verified

**No live model call has been made.** Every test uses scripted providers.
Things worth checking on the first real runs:

- whether the analyst stays neutral (the `neutrality` flag will say if it slips)
- how its witness ratings compare to the E003 scores (W001 moderate, W002 high,
  W003 low)
- whether advocates actually respond to `unsupported` reviews or ignore them
- the cost of the extra two calls - the interaction log records exact tokens

---

## Known Limitations

1. **Cross-examination and judge questions** (the stages around
   `EVIDENCE_REVIEW` in spec §14) are still not implemented.
2. **Neutrality is checked by keyword.** Subtle partiality - stressing one
   side's weaknesses more than the other's - isn't detected; that's auditor
   and evaluation work (Phases 7 and 10).
3. **Reviews inform; they don't bind.** An argument graded `unsupported` stays
   in the record. The judge is told about it, but nothing forces the judge to
   discount it.
4. **Only CASE_001 has seeded element bindings**, so it remains the only case
   the full pipeline can run.

---

**Phase 5 Completion Date**: 2026-09-18
**Next Milestone**: Phase 6 - Jury
**Overall Progress**: 5/12 phases complete (42%)

**Research Simulation Only**: This system does not provide legal advice or
determine real legal rights or obligations.
