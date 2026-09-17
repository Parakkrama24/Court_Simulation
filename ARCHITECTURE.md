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

**Location**: `backend/app/rules/`

**Purpose**: Deterministic legal rule evaluation

**Components**:
- Rule loader (JSON → LegalRule models)
- Condition evaluator
- Rule applicability checker
- Reference validator

**Workflow**:
```
Facts + Evidence → Evaluate Conditions → Determine Applicable Rules
```

### Layer 4: LLM Abstraction Layer

**Location**: `backend/app/llm/` (Future)

**Purpose**: Provider-agnostic LLM interface

**Design**:
```python
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        pass

class OpenAIProvider(LLMProvider):
    # OpenAI implementation

class AnthropicProvider(LLMProvider):
    # Anthropic implementation
```

**Benefits**:
- Swap providers without changing agent code
- A/B testing different models
- Future support for local models

### Layer 5: Agent Layer

**Location**: `backend/app/agents/` (Future)

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

**Location**: `backend/app/workflow/` (Future)

**Purpose**: LangGraph state machine for court procedure

**State**:
```python
class CourtState(TypedDict):
    case: Case
    current_stage: CourtStage
    facts: List[Fact]
    evidence: List[Evidence]
    applicable_laws: List[LegalRule]
    prosecution_arguments: List[Argument]
    defense_arguments: List[Argument]
    evidence_analysis: Dict
    jury_decisions: List[Verdict]
    judge_decision: Optional[Verdict]
    audit_report: Optional[AuditReport]
    event_history: List[Event]
```

**Workflow Stages**:
```
CASE_INITIALIZATION →
EVIDENCE_ANALYSIS →
PROSECUTION_OPENING →
DEFENSE_OPENING →
PROSECUTION_ARGUMENT →
DEFENSE_ARGUMENT →
CROSS_EXAMINATION →
EVIDENCE_REVIEW →
JUDGE_QUESTIONS →
PROSECUTION_REBUTTAL →
DEFENSE_REBUTTAL →
CLOSING_ARGUMENTS →
JURY_INDEPENDENT_DELIBERATION →
JURY_DELIBERATION →
JUDGE_DECISION →
LEGAL_PROCESS_AUDIT →
CASE_COMPLETE
```

### Layer 7: API Layer

**Location**: `backend/app/api/` (Future)

**Purpose**: HTTP and WebSocket endpoints

**Endpoints**:
- `GET /cases` - List cases
- `GET /cases/{id}` - Get case details
- `POST /cases/{id}/simulate` - Start simulation
- `WS /cases/{id}/stream` - Real-time events

**Design**:
- FastAPI for HTTP
- WebSocket for streaming
- Server-Sent Events (SSE) alternative
- CORS configuration for frontend

### Layer 8: Frontend Layer

**Location**: `frontend/` (Future)

**Purpose**: Visual courtroom simulation

**Components**:
- Case selection page
- Courtroom layout with agent visualization
- Timeline showing procedure stages
- Evidence panel
- Debate panel (prosecution vs defense)
- Jury panel
- Judge decision panel
- Audit panel

**Technology**:
- Next.js 14 with App Router
- TypeScript for type safety
- Tailwind CSS for styling
- Real-time updates via WebSocket

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

### Current Phase (Phase 1)
- In-memory case data
- No database required
- Single-threaded execution

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
