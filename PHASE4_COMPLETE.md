# Phase 4 Implementation Complete ✅

## Overview

**Phase 4: Two-Agent Adversarial System** has been implemented and tested.

**Completion Date**: 2026-09-18
**Status**: ✅ All tests passing (291/291)
**Next Phase**: Phase 5 - Evidence Agent (neutral evidence analysis)

```
                       ┌───────────── record + engine evaluation ─────────────┐
                       ▼                                                      ▼
PROSECUTION_OPENING ─► DEFENSE_OPENING ─► PROSECUTION_ARGUMENT ─► DEFENSE_ARGUMENT
  ─► PROSECUTION_REBUTTAL ─► DEFENSE_REBUTTAL ─► CLOSING_ARGUMENTS (P, then D)
  ─► JUDGE_DECISION (weighs both sides) ─► CASE_COMPLETE
```

Each advocate sees the record, the rule-engine evaluation, and every argument
presented before its turn. Every turn is validated before it enters the
record. The judge then decides with the full debate in front of it.

---

## What Was Built

### 1. Shared Agent Loop

**Location**: `backend/app/agents/base.py`

The generate → parse → validate → regenerate loop from Phase 3 now lives in
one function, `generate_validated`, used by all three agents. The judge was
moved onto it with no behaviour change: all 47 Phase 3 agent tests passed
unmodified after the refactor. `record.py` renders the one case record all
agents share.

### 2. Prosecution and Defense Agents

**Location**: `backend/app/agents/advocate/`

One `AdvocateAgent` class, configured by `AdvocateRole`. The role sets the
objective, and the stage sets the task.

| Role | Objective (from spec §5.2-5.3) |
|---|---|
| Prosecution | Strongest evidence-supported case; carries the burden (P002); map evidence to every element; challenge the defense; point out contradictions |
| Defense | Strongest evidence-supported defense; challenge evidence and witness reliability; reasonable doubt (P004); alternative interpretations; raise a defense rule only if it covers the *defendant's own* conduct |

Both share one set of ground rules: cite only record IDs, never invent or alter
facts, evidence, witnesses, or laws, and **keep assumptions apart from facts**.

**One turn** = a statement plus up to 8 arguments. Each argument carries:

```
charges        which charges it concerns
elements       [{rule_id, condition_id}] - the legal elements it addresses
claim          one or two sentences
fact_ids / evidence_ids / witness_ids / law_ids
responds_to    IDs of the opposing arguments it answers
assumptions    what it relies on that the record does not establish
reasoning, confidence
```

**Court-assigned IDs.** The model never names its own arguments. The court
assigns IDs after validation - `PR-OPEN-1`, `DF-ARG-2`, `PR-REB-1`,
`DF-CLOSE-3` (a repeated stage becomes `PR-REB2-1`) - so every `responds_to`
reference in the debate resolves to a real, attributed argument.

### 3. Advocate Validation

| Rejected (regenerate) | Why |
|---|---|
| fact / evidence / witness / rule ID not in the record | cannot invent facts, evidence, witnesses, or laws |
| element `rule_id` + `condition_id` that doesn't exist | cannot invent legal elements |
| argument cites no fact, evidence, or witness | P003 - saying it doesn't make it so |
| charge not in the case, or no charge named | cannot invent charges |
| empty turn, or more than 8 arguments | focus |
| `responds_to` names an unpresented argument | cannot answer phantom arguments |
| `responds_to` names the advocate's own side | debate is adversarial |
| rebuttal argument that answers nothing | a rebuttal must rebut |

| Recorded, not rejected | Why |
|---|---|
| relies on a disputed fact without listing any assumption | a weakness for the judge and the future auditor to see - not a hallucination |

### 4. Structured Communication

**Location**: `backend/app/domain/models.py`

- `CourtStage` - all 17 stages of the spec §14 procedure, in order
- `MessageType` - opening_statement, argument, rebuttal, closing_statement, decision
- `CourtMessage` - sender, recipient, type, stage, claim, argument IDs,
  evidence IDs, law IDs, reasoning, timestamp (spec §18)
- `Argument` gains `fact_ids` and `witness_ids`, and `ReferenceValidator`
  checks both

Every advocate turn is one `CourtMessage` to `judge_agent`, and the judgment is
a final `decision` message. Agents never exchange free-form chat.

### 5. Judge Upgrades (`judge.v2`)

- The prompt now tells the judge that arguments are advocacy, not evidence: a
  claim counts only as far as the facts and evidence it cites support it, and
  an advocate's assumption is not a fact.
- **New structural rule**: when parties have presented arguments, the judge
  must list at least one argument from *each* party in `arguments_considered`.
  Ignoring a side is rejected and regenerated (spec §9 asks: "did the judge
  consider both sides?").
- The record the judge sees includes every argument with its stage, party,
  charges, elements, citations, `responds_to`, and assumptions.

### 6. Workflow and CLI

**`app/workflow/adversarial.py`** - `run_adversarial_trial(case_id, provider, ...)`

- One provider for all agents, or separate `prosecution_provider` /
  `defense_provider` / `judge_provider` so sides can run on different models
- `stages=` accepts any plan; `check_stages` rejects impossible ones (a rebuttal
  before the other side has spoken, a non-debate stage) before any model is
  called
- `DEFAULT_DEBATE_STAGES` - 8 advocate turns + judge (9 calls)
- `QUICK_DEBATE_STAGES` - openings + closings + judge (5 calls)
- `event_history` - `AGENT_STARTED` / `AGENT_ARGUMENT` per turn (argument
  IDs, what it answered, flags, attempts), then `JUDGE_DECISION` with the
  arguments considered
- `TrialRun` - turns, messages, judgment, events, and properties for all /
  prosecution / defense arguments and total token usage

**CLI**:

```bash
python -m app.cli trial CASE_001 --show-prompt     # no API call
python -m app.cli trial CASE_001 --quick
python -m app.cli trial CASE_001 --strict --json
```

The transcript prints every turn with its arguments, citations, the arguments
it answers, its stated assumptions, and any flags, followed by the judgment and
the arguments the judge weighed.

---

## Files

**Created**:
```
backend/app/agents/base.py, record.py
backend/app/agents/advocate/   __init__, roles, schema, prompts, validation, agent
backend/app/workflow/common.py, adversarial.py
backend/tests/test_agents/test_advocate.py (33), test_trial_workflow.py (23)
```

**Modified**:
- `app/domain/models.py`, `app/domain/__init__.py` - `CourtStage`, `MessageType`,
  `CourtMessage`; `Argument.fact_ids`, `Argument.witness_ids`
- `app/rules/validator.py` - arguments' fact and witness citations checked
- `app/agents/judge/` - shared loop, shared record, `judge.v2` prompt,
  both-sides rule
- `app/workflow/judge_only.py` - uses the shared case preparation
- `app/cli.py` - `trial` command; shared run options and judgment printing
- `tests/` - both-sides tests (3), `CourtMessage` / stage tests (3), argument
  citation test (1), advocate fixtures in `test_agents/conftest.py`

---

## Tests

```
291 passed ✅ (228 from Phases 1-3, 63 new)
No network access, API keys, or vendor SDKs required.
```

- **Advocate validation**: every rejection rule above (fabricated fact,
  evidence, witness, law, element; invented or missing charge; ungrounded
  argument; empty or oversized turn; phantom or own-side `responds_to`; empty
  rebuttal) and the disputed-fact flag
- **Advocate agent**: role-specific prompts, debate-so-far in the prompt, stage
  permissions, court-assigned IDs, argument and message mapping, regeneration
  on a fabricated citation, giving up after `max_attempts`
- **Trial**: exact stage and speaker order, 16 unique attributed arguments,
  rebuttals referencing the other side, each advocate seeing only earlier
  arguments, 9 structured messages, judge receiving all arguments, event
  history, per-agent logging, a shared provider, repeated-stage IDs, the judge
  rejected for ignoring the defense then accepted, advocate failure stopping
  the trial, and stage-plan checks
- **CLI**: `--show-prompt`, a quick trial transcript, non-zero exit on failure

---

## Not Yet Verified

As in Phase 3, **no live model call has been made**. The tests prove the loop,
the validation, and the data flow with scripted providers, but not how real
models argue CASE_001. A full trial is 9 model calls with a growing record.
At Opus 5 list prices I'd *estimate* roughly $1 per full trial and about half
that with `--quick`; this is unmeasured, and the interaction log records exact
token counts on the first real run. Worth watching on those runs:

- how often each side's turns are rejected, and for what
- whether the defense wrongly raises LAW_201 (self-defense is *David's* claim,
  not the defendant's)
- whether the judge's decision moves with the debate or just follows the
  rule engine

---

## Known Limitations

1. **No cross-examination, evidence review, or judge questions.** Those stages
   sit between arguments and rebuttals in spec §14 and need the Evidence Agent
   (Phase 5) or a question-asking judge. `check_stages` rejects them for now.
2. **Still linear.** The judge can't yet request more analysis when an argument
   lacks evidence; that is a conditional transition for the LangGraph phase.
3. **Self-contradiction isn't detected.** An advocate can contradict its own
   earlier turn; detecting that is the auditor's job (Phase 7).
4. **Advocacy strength is unmeasured.** Validation guarantees arguments are
   *grounded*, not that they are *good*; quality metrics belong to Phase 10.
5. **No prompt caching yet.** Every turn resends the record. That is fine at
   this size; caching the stable record prefix is an easy win if cost matters.

---

**Phase 4 Completion Date**: 2026-09-18
**Next Milestone**: Phase 5 - Evidence Agent
**Overall Progress**: 4/12 phases complete (33%)

**Research Simulation Only**: This system does not provide legal advice or
determine real legal rights or obligations.
