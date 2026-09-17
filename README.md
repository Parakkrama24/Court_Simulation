# Multi-Agent Legal Court Simulation System

A research-oriented multi-agent AI application that simulates a fictional legal court to study how specialized AI agents can collaboratively and adversarially reason about legal cases.

**IMPORTANT DISCLAIMER**: This is a fictional legal simulation for research purposes only. This system does not provide legal advice or determine real legal rights or obligations.

## Overview

The Court Simulation System uses multiple specialized AI agents to simulate court proceedings in the fictional jurisdiction of the **Republic of Arandia**. The system maintains strict separation between facts, evidence, laws, arguments, and decisions to prevent hallucinations and ensure evidence-grounded reasoning.

## Key Features

- **Multi-Agent Architecture**: Specialized agents for prosecution, defense, evidence analysis, judge, jury, and legal auditing
- **Structured Legal Rules**: Laws defined as structured data with explicit conditions and effects
- **Evidence Grounding**: All claims must reference valid evidence IDs - fabricated references are rejected
- **Hallucination Prevention**: Validation layer ensures agents cannot invent facts, evidence, or laws
- **Observable Workflow**: LangGraph state machine tracks all court procedure stages
- **Provider Agnostic**: LLM abstraction layer supports OpenAI, Anthropic, and future local models

## Project Status

**Current Phase**: Phase 1 - Domain Models & Seed Data ✅

### Completed
- ✅ Domain models (Case, Fact, Evidence, Witness, LegalRule, Argument, Verdict, AuditReport)
- ✅ Seed data for legal principles, criminal laws, and evidence rules
- ✅ CASE_001: "The Night Intruder" - Complete with facts, evidence, and witnesses
- ✅ Comprehensive unit tests
- ✅ Project structure and configuration

### Upcoming Phases
- 🔄 Phase 2: Legal Rule Engine (deterministic rule evaluation)
- ⏳ Phase 3: Single Agent (basic LLM integration)
- ⏳ Phase 4: Two-Agent Adversarial System
- ⏳ Phase 5: Evidence Agent
- ⏳ Phase 6: Jury System
- ⏳ Phase 7: Legal Process Auditor
- ⏳ Phase 8: Full LangGraph Workflow
- ⏳ Phase 9: FastAPI Backend
- ⏳ Phase 10: Frontend Visualization
- ⏳ Phase 11: Evaluation Framework
- ⏳ Phase 12: Production Readiness

## Technology Stack

### Backend
- **Python 3.11+**
- **FastAPI** - Web framework
- **LangGraph** - Agent workflow orchestration
- **Pydantic** - Data validation
- **SQLAlchemy** - ORM
- **PostgreSQL** - Database

### AI/LLM
- **LangChain** - LLM abstraction
- **OpenAI API** - GPT models
- **Anthropic API** - Claude models
- Support for local models (future)

### Frontend (Future)
- **Next.js** - React framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling

## Project Structure

```
Court_Simulation/
├── backend/
│   ├── app/
│   │   ├── domain/              # Core domain models (Pydantic)
│   │   │   └── models.py        # Case, Fact, Evidence, etc.
│   │   ├── seed/                # Seed data loaders
│   │   │   ├── cases.py         # Test cases
│   │   │   └── legal_data.py    # Legal rules
│   │   ├── rules/               # Legal rule engine (Phase 2)
│   │   │   └── data/            # JSON legal rules
│   │   │       ├── principles.json
│   │   │       ├── criminal_laws.json
│   │   │       └── evidence_rules.json
│   │   ├── agents/              # Agent implementations (Future)
│   │   ├── workflow/            # LangGraph workflow (Future)
│   │   ├── llm/                 # LLM abstraction (Future)
│   │   └── config.py            # Configuration management
│   ├── tests/
│   │   └── test_domain/         # Domain model tests
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── pytest.ini
├── .env.example                 # Environment variables template
├── README.md
└── Promot.md                    # Original requirements
```

## Setup Instructions

### Prerequisites

- Python 3.11 or higher
- PostgreSQL (for future phases)
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Court_Simulation
   ```

2. **Create virtual environment**
   ```bash
   cd backend
   python -m venv venv

   # On Windows
   venv\Scripts\activate

   # On macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp ../.env.example ../.env
   # Edit .env with your API keys
   ```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_domain/test_models.py -v
pytest tests/test_domain/test_seed_data.py -v
```

### Current Test Results

```
Phase 1 Tests: 38/38 passing ✅
- Domain Models: 18 tests
- Seed Data: 20 tests
```

## Domain Models

### Core Entities

- **Case**: Top-level entity containing facts, evidence, witnesses, charges, and applicable laws
- **Fact**: A statement that may be established, disputed, or unknown
- **Evidence**: Information supporting or contradicting claims (cannot be modified by agents)
- **Witness**: Person providing testimony with reliability factors
- **LegalRule**: Structured legal rule with conditions and effects
- **Argument**: Claim made by an agent with evidence and law references
- **Verdict**: Decision by judge or jury with reasoning
- **AuditReport**: Quality assessment of the simulation process

### Legal Rules

**Principles** (5 rules):
- P001: Presumption of Innocence
- P002: Burden of Proof
- P003: Evidence Requirement
- P004: Reasonable Doubt
- P005: Evidence Consistency

**Criminal Laws** (7 rules):
- LAW_101: Assault
- LAW_102: Aggravated Assault
- LAW_103: Theft
- LAW_104: Burglary
- LAW_201: Self Defense
- LAW_202: Excessive Defensive Force
- LAW_301: Attempt

**Evidence Rules** (5 rules):
- E001: Direct Evidence
- E002: Circumstantial Evidence
- E003: Witness Reliability
- E004: Conflicting Evidence
- E005: Fabricated Evidence

## Test Cases

### CASE_001: The Night Intruder

A home invasion and alleged self-defense case.

**Summary**: Alex Johnson entered David Thompson's home without permission at 11:45 PM through a broken window. David confronted Alex and struck him with a baseball bat, causing serious injuries. Alex is charged with burglary and assault. David claims self-defense.

**Key Issues**:
- Unauthorized entry (burglary)
- Self-defense validity
- Proportionality of defensive force
- Reasonable belief of threat

**Case Components**:
- 8 Facts (established and disputed)
- 8 Evidence items (physical, forensic, digital, testimonial)
- 3 Witnesses (David, neighbor Margaret, Alex)
- 2 Charges (burglary, assault)
- 5 Applicable laws

## Architecture Principles

1. **Separation of Concerns**: Facts, evidence, laws, arguments, and decisions are separate entities
2. **Evidence Grounding**: All agent claims must reference valid IDs from the case database
3. **No Hallucination**: Validation rejects any fabricated references before acceptance
4. **Observability**: All agent actions recorded in event history
5. **Reproducibility**: Structured data and deterministic rule engine
6. **Modularity**: Clean separation between domain, agents, workflow, rules, and LLM

## Future Agents

### Planned Agent Types

- **Case Manager**: Initializes cases and manages workflow
- **Prosecution Agent**: Builds evidence-supported prosecution case
- **Defense Agent**: Challenges prosecution and presents defense
- **Evidence Agent**: Neutral analysis of evidence reliability
- **Judge Agent**: Procedural authority and decision-making
- **Jury Agents** (3): Independent deliberation and verdicts
- **Legal Process Auditor**: Detects violations and assesses quality

## Contributing

This is a research project. Contributions should focus on:
- Maintaining evidence grounding and hallucination prevention
- Clear separation of facts, evidence, and arguments
- Comprehensive testing
- Documentation

## License

[To be determined]

## Research Goals

This system aims to explore:
1. Multi-agent adversarial reasoning
2. Evidence-grounded legal argumentation
3. Hallucination prevention in LLM applications
4. Structured vs. unstructured legal knowledge
5. Agent consistency and reasoning quality
6. Verdict agreement among independent agents

## Contact

[To be determined]

---

**Research Simulation Only**: This system does not provide legal advice or determine real legal rights or obligations.
