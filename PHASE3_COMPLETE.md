# Phase 3 Implementation Complete ✅

## Overview

**Phase 3: Single Agent** has been implemented and tested.

**Completion Date**: 2026-09-18
**Status**: ✅ All tests passing (228/228)
**Next Phase**: Phase 4 - Two-Agent Adversarial System (Prosecution ↔ Defense → Judge)

Phase 3 validates the basic LLM integration with one agent:

```
Case ──► Rule Engine (Phase 2) ──► Judge Agent ──► Validation ──► Decision
                                        ▲               │
                                        └── rejected ───┘
                                     (reasons fed back, regenerate)
```

The judge sees the case record *and* the deterministic rule-engine
evaluation. Its output is structured JSON, and every ID it cites is checked
against the record before the decision is accepted.

---

## What Was Built

### 1. Provider-Agnostic LLM Layer

**Location**: `backend/app/llm/`

| File | Role |
|---|---|
| `base.py` | `LLMProvider` interface, `LLMRequest` / `LLMResponse`, typed errors |
| `anthropic_provider.py` | Claude via the Anthropic SDK |
| `openai_provider.py` | OpenAI **and** any OpenAI-compatible local server |
| `scripted.py` | Replays canned responses - drives every agent test |
| `schema.py` | Pydantic model → strict JSON schema both vendors accept |
| `interaction_log.py` | Records every model call |
| `factory.py` | `LLM_PROVIDER` → concrete provider |

**No vendor lock-in**: agents import only `LLMProvider`. SDKs are imported
lazily inside each provider, so the test suite and the `--show-prompt` path run
with neither SDK installed.

**Anthropic provider**: defaults to `claude-opus-5`; structured output through
`output_config.format`; `effort` configurable (`ANTHROPIC_EFFORT`, default
`high`). **Server-side refusal fallback is enabled by default**
(`fallbacks: "default"`): if the model's safety classifiers decline a request,
the API re-runs it on Anthropic's recommended fallback model in the same call.
Turn it off with `ANTHROPIC_REFUSAL_FALLBACK=False`.

**OpenAI-compatible provider**: strict `json_schema` response format by
default; `json_mode` for local servers that can't constrain output to a
schema (the schema is still enforced by validation after parsing). The
`local` provider targets Ollama at `http://localhost:11434/v1` by default.

**Failures are typed, not silent**: a refusal raises `LLMRefusalError`, and
hitting the token ceiling raises `LLMTruncatedError`. Neither is ever returned
as though it were an answer.

### 2. Interaction Logging

Every call - accepted, rejected, or failed - is recorded with the fields
spec §22 requires:

| Field | Source |
|---|---|
| agent, case, attempt | the calling agent |
| prompt version | `judge.v1` |
| provider, model | the response (the model that actually served it) |
| timestamp | UTC, ISO 8601 |
| input state | the full request (system prompt + conversation) and its SHA-256 |
| output | the raw model text |
| token usage | input / output / cache-read tokens |
| latency | wall-clock milliseconds |
| validation result | passed / failed + every rejection reason, or the provider error |

Written to memory and, via the CLI, to `logs/llm_interactions.jsonl`
(git-ignored, since it contains full prompts and outputs).

**No hidden chain-of-thought** is requested or stored. Only final text blocks
are read from responses; the judge is asked for concise, checkable rationales.

### 3. Judge Agent

**Location**: `backend/app/agents/judge/`

| File | Role |
|---|---|
| `schema.py` | Output contract (`JudgeDecisionOutput`) |
| `prompts.py` | Versioned system prompt + deterministic record rendering |
| `validation.py` | Reference, structural, and engine-alignment checks |
| `agent.py` | Generate → parse → validate → regenerate loop |

**Output contract** - the six separations spec §7 requires, as data:

```
established_facts     [fact_id, finding, evidence_ids]
disputed_facts        [fact_id, issue, supporting/contradicting evidence, resolution]
applicable_rules      [rule_id, relevance]
arguments_considered  [argument_id]          (empty in Phase 3 - no parties yet)
analysis              text
charge_decisions      [charge, rule_id, elements[condition_id, assessment, fact_ids,
                       evidence_ids, reasoning], defenses_considered, decision, confidence]
unresolved_questions, overall_confidence
```

**The prompt** states the six principles and the record-only rule, then gives
the record as JSON: facts, evidence, witnesses, the applicable laws plus all
principles and evidence rules, and the full rule-engine evaluation (per rule,
per subject, per condition, with strengths and cited IDs). It is rendered in a
stable order, so the same case always produces a byte-identical prompt.

### 4. Validation - Three Layers

| Layer | Catches | Outcome |
|---|---|---|
| **References** | fact, evidence, rule, or argument IDs not in the record | always rejected |
| **Structure** | charge undecided / decided twice / invented; offense decided under a non-offense rule; non-defense listed as a defense; unknown condition; required element not assessed; **guilty on an element the judge itself didn't find established** | always rejected |
| **Engine alignment** | conviction where the engine didn't find the offense satisfied; element found established that the engine found unsatisfied or unsupported (and the reverse); disputed fact treated as established | recorded as `EngineDivergence`, with the direction (for/against the defendant) |

Engine divergences are **recorded, not rejected, by default**. The engine
weighs hand-authored bindings with fixed thresholds; a judge may reasonably
disagree, and *how often and in which direction* models disagree is exactly
what Phase 10's evaluation needs to measure. `--strict` (or
`strict_engine_alignment=True`) turns convictions the engine doesn't support
into rejections.

### 5. Reject and Regenerate

When a decision fails validation, the model sees its own previous output
followed by the exact rejection reasons, and is asked for a corrected, complete
decision. After `LLM_MAX_ATTEMPTS` (default 3) rejections the agent raises
`JudgeAgentError` with every attempt attached. **An unvalidated decision is
never returned.** A refusal or other provider error fails immediately (the
SDKs already retry transient network errors).

### 6. Workflow and CLI

**`app/workflow/judge_only.py`** runs the linear pipeline and records an
`event_history`:

```
CASE_INITIALIZATION/CASE_LOADED → RULE_EVALUATION/RULES_EVALUATED →
JUDGE_DECISION/AGENT_STARTED → JUDGE_DECISION/JUDGE_DECISION → CASE_COMPLETE
```

It also re-validates the seeded bindings before evaluating, so a broken seed
fails the run rather than quietly skewing the judge's input.

**`app/cli.py`**:

```bash
python -m app.cli judge CASE_001 --show-prompt        # no API call, no key
python -m app.cli judge CASE_001 --provider anthropic
python -m app.cli judge CASE_001 --provider local --model llama3.1
python -m app.cli judge CASE_001 --strict --max-attempts 5
python -m app.cli judge CASE_001 --json
```

The judge's verdict is mapped onto the Phase 1 `Verdict` model. The per-charge
decisions, prompt version, model, attempt count, engine divergences, and the
research disclaimer are kept in its metadata.

---

## Files

**Created**:
```
backend/app/llm/            __init__, base, schema, anthropic_provider,
                            openai_provider, scripted, interaction_log, factory
backend/app/agents/         __init__
backend/app/agents/judge/   __init__, schema, prompts, validation, agent
backend/app/workflow/       __init__, judge_only
backend/app/cli.py

backend/tests/test_llm/     test_providers (16), test_llm_support (22)
backend/tests/test_agents/  conftest, test_judge_validation (19),
                            test_judge_agent (17), test_judge_workflow (11)
```

**Modified**:
- `backend/app/config.py` - Anthropic default `claude-opus-5` (the old
  `claude-3-5-sonnet-20241022` default is retired); OpenAI default `gpt-4o`
  (`gpt-4-turbo-preview` doesn't support strict structured outputs); effort,
  refusal fallback, local-model, attempt-limit, and log-path settings; `.env`
  is now found in either `backend/` or the repository root. Previously the
  README's `cp ../.env.example ../.env` produced a file the app never read when
  run from `backend/`.
- `.env.example` - the new settings
- `backend/requirements.txt` - `anthropic>=1,<2`, `openai>=1.40,<3`
- `.gitignore` - `logs/`

---

## Tests

```
228 passed ✅ (143 from Phases 1-2, 85 new)
No network access, API keys, or vendor SDKs required.
```

- **Providers**: exact request shape for both vendors (model, system prompt,
  roles, schema format, effort, fallback header), response parsing, thinking
  blocks excluded, refusal / truncation / SDK errors surfaced as typed errors -
  all against fake clients
- **Support**: strict schema generation (refs inlined, objects closed, property
  names like `title` preserved), scripted provider, log fields, JSONL output,
  stable request hashing, factory and settings mapping
- **Validation**: every reference, structural, and divergence rule, each staged
  by mutating one field of a known-good CASE_001 decision
- **Agent**: accept on the first attempt; reject-then-accept for fabricated
  IDs, malformed JSON, schema mismatch, and out-of-range confidence; the
  conversation grows by exactly the rejected output plus its reasons; gives up
  after `max_attempts`; refusals fail loudly and are logged; strict mode forces
  regeneration
- **Workflow / CLI**: end-to-end run, event order, the judge receives the
  engine's evaluation, `--show-prompt` makes no call, failures exit non-zero

---

## Not Yet Verified

**No live model call has been made.** Every test uses scripted or fake
providers, which proves the loop, validation, and request shape, but not how a
real model performs on CASE_001. The Anthropic SDK was not installed in the
development environment. The OpenAI provider was checked against the installed
SDK's real signature and client construction, but not against the live API.

To run it for real:

```bash
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...          # or set it in .env
python -m app.cli judge CASE_001 --provider anthropic
```

The first live runs are worth reading closely - in particular whether the model
convicts on anything the engine left indeterminate, and how many attempts it
needs.

---

## Known Limitations

1. **Only CASE_001 is runnable end-to-end** - it is still the only seeded case
   with element bindings.
2. **Linear pipeline, not LangGraph yet.** `event_history` is a plain list; the
   full court procedure state machine is a later phase.
3. **Synchronous calls.** Fine for one agent; parallel jury calls will want the
   async clients.
4. **The subject of a charge is assumed to be `case.defendant`.** That holds for
   the seeded cases, where every charge is against one defendant.
5. **Local models vary.** In `json_mode` a local model can return well-formed
   JSON of the wrong shape; the regeneration loop handles it, but small models
   may exhaust their attempts.

---

**Phase 3 Completion Date**: 2026-09-18
**Next Milestone**: Phase 4 - Two-Agent Adversarial System
**Overall Progress**: 3/12 phases complete (25%)

**Research Simulation Only**: This system does not provide legal advice or
determine real legal rights or obligations.
