# Architecture Documentation

## System Overview

The Multi-Agent Legal Court Simulation System is designed as a research platform to study how multiple specialized AI agents can collaboratively and adversarially reason about legal cases while maintaining strict evidence grounding and preventing hallucinations.

## Core Architectural Principles

### 1. Separation of Concerns

The system maintains strict separation between:

- **Domain Models**: Pure data structures (Pydantic models)
- **Legal Rules**: Structured JSON with conditions and effects
- **Agent Logic**: Specialized reasoning agents
- **Workflow**: LangGraph state machine
- **LLM Providers**: Abstracted behind interfaces
- **Database**: SQLAlchemy ORM models
- **API**: FastAPI endpoints
- **Frontend**: Next.js UI

### 2. Evidence Grounding

**Problem**: LLMs may hallucinate facts, evidence, or legal rules.

**Solution**: All agent outputs must reference valid IDs from the authoritative case database.

**Implementation**:
- Agents reference evidence_id, fact_id, law_id, witness_id
- Validation layer verifies all IDs exist before accepting output
- Invalid references are rejected and agents must regenerate
- Violations are logged in the audit report

### 3. Immutable Evidence

**Principle**: Agents interpret evidence but cannot modify it.

**Implementation**:
- Evidence is loaded from the case database
- Agents can only reference evidence in arguments
- Evidence metadata includes reliability scores
- Evidence Agent analyzes but does not change evidence

### 4. Structured Legal Rules

**Design**: Legal rules are not just prompts - they are structured data.

**Format**:
```json
{
  "rule_id": "LAW_201",
  "name": "Self Defense",
  "category": "defense",
  "conditions": [
    {
      "id": "C1",
      "description": "Reasonable belief of unlawful attack",
      "required": true
    }
  ],
  "effect": "self_defense_may_apply"
}
```

**Benefits**:
- Deterministic condition evaluation
- Clear required elements
- Testable rule application
- Jurisdiction-specific rules

### 5. Observable Workflow

**Goal**: Every agent action must be traceable.

**Implementation**:
- LangGraph state contains event_history
- All agent outputs are structured messages
- Every stage transition is recorded
- Complete audit trail for research analysis

## System Layers

### Layer 1: Domain Layer

**Location**: `backend/app/domain/`

**Purpose**: Core business entities

**Models**:
- Case, Fact, Evidence, Witness
- LegalRule, Condition
- Argument, Verdict, AuditReport

**Characteristics**:
- Pure Pydantic models
- No database dependencies
- No LLM dependencies
- Fully testable

### Layer 2: Data Layer

**Location**: `backend/app/database/` (Future)

**Purpose**: Persistence and data access

**Components**:
- SQLAlchemy ORM models
- Database connection management
- Repository pattern for data access
- Alembic migrations

**Design**:
- Separation between domain models and database models
- Repository pattern hides database details
- Transaction management

### Layer 3: Rules Engine

**Location**: `backend/app/rules/` (implemented in Phase 2)

**Purpose**: Deterministic legal rule evaluation

**Components**:
- `registry.py` - indexed, read-only access to the jurisdiction's rules
- `evaluator.py` - condition evaluation and witness reliability (E003)
- `engine.py` - rule and case evaluation, conflict detection (E004)
- `validator.py` - reference validation (anti-hallucination gate)
- `models.py` - evaluation results and the tunable `EvaluationPolicy`

**Workflow**:
```
Facts + Evidence --(element bindings)--> Conditions --> Rule status --> Effects
```

**Element bindings**: conditions are natural language, so an `ElementBinding`
states which facts and evidence bear on a given condition, for a given party.
Bindings are *input* to the engine - they never carry a conclusion. An agent
may propose them (Phase 5), the validator checks their IDs, and the engine
computes the outcome. This keeps the authoritative legal layer deterministic
while leaving interpretation to the LLM.

**Statuses**:
- Condition: `satisfied` / `disputed` / `unsatisfied` / `unsupported`
- Rule: `satisfied` / `not_satisfied` / `indeterminate` / `unconditional`

`unsupported` and `indeterminate` are deliberately distinct from
`unsatisfied`: an element nobody addressed is not an element that was
disproved, and the burden of proof (P002) and reasonable doubt (P004) both
turn on that difference.

**Rule dependencies**: a condition may declare `depends_on_rule` (LAW_102's
assault element resolves through LAW_101 for the same subject). Cycles are
detected and reported rather than recursed.

### Layer 4: LLM Abstraction Layer

**Location**: `backend/app/llm/` (implemented in Phase 3)

**Purpose**: Provider-agnostic LLM interface

**Design**:
```python
class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse: ...
```

`LLMRequest` carries the system prompt, the conversation, and an optional JSON
schema; `LLMResponse` carries the final text (never hidden reasoning), token
usage, latency, and the provider's request ID. Refusals and truncation are
raised as typed errors (`LLMRefusalError`, `LLMTruncatedError`) rather than
returned as if they were answers.

**Providers**:
- `AnthropicProvider` - Anthropic Messages API; structured output through
  `output_config.format`; server-side refusal fallback on by default
- `OpenAICompatibleProvider` - Chat Completions with strict `json_schema`;
  with `base_url` it serves OpenAI and local servers (Ollama, vLLM, LM Studio);
  `json_mode` for servers without schema-constrained output
- `ScriptedProvider` - replays canned responses; powers every agent test

`strict_json_schema()` turns a Pydantic model into the conservative schema
dialect both vendors enforce (closed objects, all fields required, no refs).
Range constraints are dropped from the provider schema but still enforced by
Pydantic after parsing.

**Interaction log** (`interaction_log.py`): every call records agent, case,
prompt version, attempt, provider, model, timestamp, a SHA-256 of the full
request, the request itself, the output, token usage, latency, and the
validation outcome - to memory and optionally to a JSON Lines file.

### Layer 5: Agent Layer

**Location**: `backend/app/agents/` (Judge in Phase 3; Prosecution and Defense in Phase 4;
Evidence in Phase 5; Jury in Phase 6; Auditor in Phase 7)

**Implemented design**: every agent runs through one loop in `agents/base.py` -
generate structured JSON, parse, validate against the record, and on failure
show the model its own output with the exact reasons and regenerate. After
`max_attempts` rejections the agent raises; unvalidated output is never
returned. All agents see the same record, rendered by `agents/record.py`.

Prosecution and Defense are one `AdvocateAgent` class configured by role.
Arguments get court-assigned IDs after validation, and each turn becomes a
`CourtMessage` - the structured communication format of spec section 18.

The Evidence Agent's analysis and argument reviews are passed into the shared
record as plain data (`evidence_context`), so every later speaker sees them
without the agents depending on one another. Anything that is a fact about
the record rather than an interpretation - evidence provenance, the E003
witness scores - is computed in code and given to the model, never asked of it.

Jury independence is structural: a juror's independent-round request is
built from the trial record alone, with no parameter through which another
juror's decision could enter. The verdict engine (`jury/aggregation.py`)
that turns votes into a verdict is deterministic code, and only the judge
receives the jury's result.

The Legal Process Auditor closes a trial. It is two layers: deterministic
checks over the finished run (`workflow/audit.py`) and an auditor agent for
what code cannot judge. Both produce `AuditFinding`s, filed by category into
the domain `AuditReport`. Because the checks take a finished `TrialRun`, a
run saved as JSON can be re-audited later without re-running the trial -
which is what the evaluation phase will need.

**Purpose**: Specialized reasoning agents

**Base Agent**:
```python
class BaseAgent(ABC):
    def __init__(self, llm: LLMProvider, validator: Validator):
        self.llm = llm
        self.validator = validator

    @abstractmethod
    def execute(self, state: CourtState) -> AgentOutput:
        pass

    def validate_output(self, output: AgentOutput) -> bool:
        # Verify all referenced IDs exist
        pass
```

**Specialized Agents**:

1. **Case Manager Agent**
   - Initializes cases
   - Manages workflow transitions
   - No decision-making authority

2. **Evidence Agent**
   - Neutral analysis
   - Identifies supported/contradicted claims
   - Evaluates witness reliability
   - Cannot advocate for either side

3. **Prosecution Agent**
   - Builds strongest prosecution case
   - Maps evidence to legal elements
   - Identifies offense conditions
   - Restricted: Cannot invent facts/evidence/laws

4. **Defense Agent**
   - Builds strongest defense
   - Challenges prosecution arguments
   - Identifies reasonable doubt
   - Restricted: Same as prosecution

5. **Judge Agent**
   - Procedural authority
   - Asks clarifying questions
   - Evaluates legal elements
   - Must remain neutral

6. **Jury Agents** (3 independent)
   - Independent deliberation
   - No communication until deliberation phase
   - Each produces verdict with reasoning

7. **Legal Process Auditor**
   - Inspects simulation quality
   - Detects hallucinations
   - Identifies violations
   - Reports only - no decision authority

### Layer 6: Workflow Layer

**Location**: `backend/app/workflow/` (implemented in Phase 8)

**Purpose**: The court procedure of spec section 14

**Design**: three layers.

- `steps.py` - each stage as one function: it runs the agents for that stage
  and returns what they produced plus the events and messages to record. A
  `Court` holds what does not change during a trial (case, evaluation,
  agents, options); `open_court` checks the whole configuration before any
  model is called.
- `graph.py` - the full procedure as a LangGraph `StateGraph`. Each node runs
  a step and returns only what it adds to the state; conditional edges choose
  the branch (evidence on/off, cross-examination, judge questions, jury,
  deliberation, audit).
- `adversarial.py` - a linear runner over the same steps, for custom stage
  plans (any order, repeated stages).

Both produce a `TrialRun` (`run.py`), which the audit, the CLI, and saved JSON
runs all work from.

**State** (`CourtState`, a `TypedDict`): every spec section 17 field, plus
the working state the steps need. Append-only fields use `operator.add`
reducers, so a node returns just its additions:

```python
class CourtState(TypedDict, total=False):
    case: Case
    current_stage: str
    facts: List[Fact]
    evidence: List[Evidence]
    applicable_laws: List[LegalRule]
    prosecution_arguments: Annotated[List[Argument], operator.add]
    defense_arguments: Annotated[List[Argument], operator.add]
    evidence_analysis: Optional[EvidenceAnalysis]
    judge_questions: Annotated[List[JudgeQuestion], operator.add]
    jury_decisions: Annotated[List[Verdict], operator.add]
    judge_decision: Optional[Verdict]
    audit_report: Optional[AuditReport]
    event_history: Annotated[List[Dict[str, Any]], operator.add]
    # ... plus arguments, turns, messages, reviews, question rounds,
    #     jury rounds, judgment, audit
```

**Conditional transitions**:

| After | Goes to | When |
|---|---|---|
| CASE_INITIALIZATION | EVIDENCE_ANALYSIS / PROSECUTION_OPENING | Evidence Agent on / off |
| DEFENSE_ARGUMENT | CROSS_EXAMINATION / EVIDENCE_REVIEW / PROSECUTION_REBUTTAL | cross-examination on; else evidence on; else neither |
| EVIDENCE_REVIEW | JUDGE_QUESTIONS / PROSECUTION_REBUTTAL | an argument is unsupported and question rounds remain |
| review of answers | JUDGE_QUESTIONS / PROSECUTION_REBUTTAL | an answer is still unsupported and rounds remain |
| CLOSING_ARGUMENTS | JURY_INDEPENDENT_DELIBERATION / JUDGE_DECISION | jury on / off |
| JURY_INDEPENDENT_DELIBERATION | JURY_DELIBERATION / verdict engine | deliberation on with 2+ jurors |
| JUDGE_DECISION | LEGAL_PROCESS_AUDIT / CASE_COMPLETE | audit on / off |

The judge-questions loop is the spec's "the Judge should be able to request
additional analysis if an argument lacks evidence", bounded by
`max_question_rounds`. A stage that does not run is recorded as a
`STAGE_SKIPPED` event with its reason.

**Live events**: `run_court(..., on_event=...)` is called with every event as
nodes complete - the hook the streaming phase will build on.

### Layer 7: API Layer

**Location**: `backend/app/api/` (implemented in Phase 9)

**Purpose**: HTTP access to cases, rules, and simulations

**Structure**:
- `app.py` - `create_app()`, CORS from settings, `/health`, the OpenAPI docs
- `routers/cases.py` - cases and legal rules (read-only)
- `routers/simulations.py` - starting runs and following them
- `runs.py` - the run manager: a run per background thread, its events, its
  result
- `schemas.py` - the API's own request and response models, separate from the
  domain models
- `dependencies.py` - settings, the LLM provider factory, the run manager

**Why runs are asynchronous**: a trial is minutes of model calls, far longer
than an HTTP request should live. `POST /api/cases/{id}/simulate` validates
the request, starts a background thread, and returns `202` with a run ID. The
client polls `/events?after=N` or subscribes to `/stream`, and reads the
result from `/runs/{id}` once the status is terminal. Errors do not escape the
thread: a failed run is recorded with its reason and reported as `failed`.

**Streaming** (spec section 21) uses Server-Sent Events over the existing
`on_event` hook from the workflow. Each message's event name is the court
event type - `AGENT_ARGUMENT`, `JURY_DECISION`, `AUDIT_COMPLETED` - so a
browser can listen for the ones it needs. The stream reads the run's own event
list from an index, so a late subscriber still receives everything from the
beginning.

**The provider is a dependency**, not a global, so tests (and other
deployments) supply their own. That is how the API test suite runs every
endpoint, including a full trial, without a network or an API key.

### Layer 8: Frontend Layer

**Location**: `frontend/` (implemented in Phase 10)

**Purpose**: The visual courtroom dashboard (spec section 20)

**Structure**:
- `app/` - App Router pages: case selection, the case record, the live run,
  the run list, and the legal rules
- `components/` - the courtroom bench, the timeline, the live event feed, and
  `panels/` for evidence, legal rules, debate, jury, judge decision, and audit
- `hooks/useRunStream.ts` - one run, followed live
- `lib/` - the typed API client, the API contract in TypeScript, and the
  derivation of court state from the event stream

**Everything runs in the browser.** The backend allows the dashboard's origin
through CORS and the stream is an `EventSource`, so there is no reason to
proxy reads through the Next.js server. That keeps one source of truth: the
API.

**Two sources of state, kept apart**:
- while a run is going, every panel is derived from the event stream alone
  (`lib/runState.ts`), because that is all the backend has published;
- once the run is terminal, the dashboard reads `/api/runs/{id}` and renders
  the full result.

A panel that cannot yet show something says so rather than inventing a
placeholder - the same rule the agents work under.

**Streaming** subscribes to each court event type by name (spec section 21).
If the browser cannot keep the stream open, the hook falls back to polling
`/api/runs/{id}/events?after=N`. The backend numbers events and a stream
always replays from the first one, so a reconnect loses and repeats nothing.

**Technology**: Next.js 16 (App Router), TypeScript, Tailwind CSS 4, tested
with Vitest and Testing Library.

## Data Flow

### Simulation Execution Flow

```
1. User selects case
   ↓
2. Backend loads case from database
   ↓
3. LangGraph initializes CourtState
   ↓
4. Workflow executes stages sequentially
   ↓
5. Each stage:
   - Agent generates output
   - Validator checks references
   - If valid: Accept and update state
   - If invalid: Reject and request regeneration
   ↓
6. Events streamed to frontend in real-time
   ↓
7. Simulation completes
   ↓
8. Audit report generated
   ↓
9. Results stored in database
```

### Agent Interaction Pattern

```
Agent receives state
  ↓
Agent builds prompt with:
  - Role description
  - Current stage
  - Available facts/evidence/laws
  - Previous arguments
  ↓
LLM generates output
  ↓
Agent parses output into structured format
  ↓
Validator checks:
  - Evidence IDs exist?
  - Fact IDs exist?
  - Law IDs exist?
  - Witness IDs exist?
  ↓
If valid: Return output
If invalid: Log violation, request regeneration
```

## Hallucination Prevention

### Strategy

1. **ID-Based References**: All claims must cite IDs, not just descriptions
2. **Validation Layer**: Automated checking before acceptance
3. **Structured Outputs**: Use Pydantic for output parsing
4. **Rejection + Regeneration**: Invalid outputs are rejected
5. **Audit Trail**: All violations logged for analysis

### Validation Rules

```python
def validate_argument(argument: Argument, case: Case) -> ValidationResult:
    errors = []

    # Check evidence references
    valid_evidence_ids = {e.evidence_id for e in case.evidence}
    for eid in argument.evidence_ids:
        if eid not in valid_evidence_ids:
            errors.append(f"Invalid evidence_id: {eid}")

    # Check law references
    valid_law_ids = {law_id for law_id in case.applicable_laws}
    for lid in argument.law_ids:
        if lid not in valid_law_ids:
            errors.append(f"Invalid law_id: {lid}")

    if errors:
        return ValidationResult(valid=False, errors=errors)

    return ValidationResult(valid=True, errors=[])
```

## Scalability Considerations

### Current Phase (Phase 10)
- In-memory case data and evaluations
- No database required
- Single-threaded, deterministic execution

### Future Phases
- PostgreSQL for case storage
- Async execution where possible
- Parallel jury deliberation
- Caching of rule evaluations
- Streaming responses

## Testing Strategy

### Unit Tests
- Domain models: Pydantic validation
- Rule engine: Condition evaluation
- Validators: ID verification

### Integration Tests
- Workflow execution
- Agent interactions
- End-to-end simulation

### Evaluation Tests
- Hallucination rate
- Reasoning consistency
- Verdict agreement
- Evidence grounding

## Security & Privacy

### Current Scope (Fictional Cases)
- All cases are fictional
- No real personal information
- No actual legal decisions

### Future Considerations
- Secure API endpoints
- User authentication if multi-user
- Rate limiting
- Input sanitization

## Performance Targets

- Case initialization: < 1 second
- Agent reasoning: 2-10 seconds per stage
- Full simulation: 2-5 minutes
- Frontend updates: Real-time (< 500ms latency)

## Monitoring & Observability

### Logging

Every LLM interaction logged:
- Agent ID
- Timestamp
- Input state
- Output
- Token usage
- Validation result

### Metrics

- Hallucination rate per agent
- Average confidence scores
- Verdict agreement rate
- Reasoning consistency score
- Processing time per stage

## Future Enhancements

1. **Vector Database**: Semantic search over large legal corpora
2. **Multi-Jurisdiction**: Support real legal systems
3. **Interactive Mode**: Allow users to inject questions
4. **Comparative Analysis**: Run same case with different models
5. **Explanation Generation**: Natural language explanation of decisions
6. **Appeal Simulation**: Multi-level court hierarchy

## References

- Original requirements: `Promot.md`
- Domain models: `backend/app/domain/models.py`
- Legal rules: `backend/app/rules/data/`
- Test cases: `backend/app/seed/cases.py`

---

**Last Updated**: 2024-09-17 (Phase 1)
