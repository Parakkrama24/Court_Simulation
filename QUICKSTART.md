# Quick Start Guide

## Phase 8 Complete ✅

This guide will help you get started with the Court Simulation System. Currently, Phase 1 (Domain Models & Seed Data), Phase 2 (Legal Rule Engine), Phase 3 (Judge Agent), Phase 4 (Prosecution ↔ Defense → Judge), Phase 5 (Evidence Agent), Phase 6 (Jury), Phase 7 (Legal Process Auditor), and Phase 8 (Full LangGraph Workflow) are complete.

## What's Working Now

- ✅ Complete domain models (Pydantic)
- ✅ Structured legal rules (JSON)
- ✅ CASE_001 seed data with facts, evidence, and witnesses
- ✅ 517 passing unit tests
- ✅ Configuration management
- ✅ Project structure

## Installation

### 1. Prerequisites

- Python 3.11 or higher
- Git
- pip

### 2. Clone and Setup

```bash
# Navigate to project
cd Court_Simulation/backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running Tests

### Run All Tests

```bash
cd backend
pytest
```

Expected output:
```
517 tests passed ✅
```

### Run Specific Tests

```bash
# Domain models tests
pytest tests/test_domain/test_models.py -v

# Seed data tests
pytest tests/test_domain/test_seed_data.py -v

# Rule engine tests
pytest tests/test_rules -v
```

### Run with Coverage

```bash
pytest --cov=app --cov-report=term-missing
```

## Exploring the Data

### Load and Inspect CASE_001

```python
from app.seed import get_case_by_id

# Load the case
case = get_case_by_id("CASE_001")

# Inspect case details
print(f"Case: {case.title}")
print(f"Defendant: {case.defendant}")
print(f"Charges: {case.charges}")
print(f"Facts: {len(case.facts)}")
print(f"Evidence: {len(case.evidence)}")
print(f"Witnesses: {len(case.witnesses)}")

# Inspect specific evidence
for evidence in case.evidence:
    print(f"\n{evidence.evidence_id}: {evidence.description}")
    print(f"  Type: {evidence.type}")
    print(f"  Reliability: {evidence.reliability}")
    print(f"  Supports: {evidence.supports}")
```

### Load Legal Rules

```python
from app.seed import get_all_legal_rules, get_legal_rules_by_category
from app.domain import LegalCategory

# Get all rules
all_rules = get_all_legal_rules()
print(f"Total rules: {len(all_rules)}")

# Get specific categories
principles = get_legal_rules_by_category(LegalCategory.PRINCIPLE)
offenses = get_legal_rules_by_category(LegalCategory.OFFENSE)
defenses = get_legal_rules_by_category(LegalCategory.DEFENSE)

print(f"Principles: {len(principles)}")
print(f"Offenses: {len(offenses)}")
print(f"Defenses: {len(defenses)}")

# Inspect self-defense rule
self_defense = next(r for r in defenses if r.rule_id == "LAW_201")
print(f"\n{self_defense.name}")
print(f"Conditions:")
for condition in self_defense.conditions:
    print(f"  - {condition.description}")
```

## Project Structure Overview

```
backend/
├── app/
│   ├── domain/
│   │   ├── __init__.py
│   │   └── models.py           # ✅ All domain models
│   ├── seed/
│   │   ├── __init__.py
│   │   ├── cases.py            # ✅ CASE_001 data
│   │   └── legal_data.py       # ✅ Legal rules loader
│   ├── rules/
│   │   └── data/
│   │       ├── principles.json      # ✅ 5 principles
│   │       ├── criminal_laws.json   # ✅ 7 laws
│   │       └── evidence_rules.json  # ✅ 5 rules
│   └── config.py               # ✅ Configuration
├── tests/
│   └── test_domain/
│       ├── test_models.py      # ✅ 18 tests
│       └── test_seed_data.py   # ✅ 20 tests
│   └── test_rules/             # ✅ 105 tests
├── requirements.txt
├── pyproject.toml
└── pytest.ini
```

## Understanding the Domain

### Core Entities

1. **Case** - Top-level container
   - Contains: facts, evidence, witnesses, charges, applicable laws
   - Status: initialized, in_progress, completed, archived

2. **Fact** - Statements about what happened
   - Status: established, disputed, unknown
   - Source: where the fact came from

3. **Evidence** - Information supporting or contradicting claims
   - Types: physical, testimonial, documentary, digital, forensic, circumstantial
   - Immutable: agents cannot modify evidence
   - References: supports/contradicts other claims

4. **Witness** - Person providing testimony
   - Has reliability factors (bias, opportunity, memory, etc.)
   - Linked to related evidence

5. **LegalRule** - Structured law definition
   - Has conditions (elements that must be proven)
   - Has effect (what happens when conditions met)
   - Categories: offense, defense, principle, evidence_rule

6. **Argument** - Claims made by agents
   - Must reference valid evidence_ids and law_ids
   - Includes reasoning and confidence

7. **Verdict** - Decision by judge or jury
   - Must cite evidence and laws used
   - Includes reasoning and confidence

8. **AuditReport** - Quality assessment
   - Detects hallucinations and violations
   - Checks evidence, legal, and procedural integrity

## CASE_001: The Night Intruder

### Summary

Alex Johnson entered David Thompson's home at 11:45 PM through a broken window. David confronted Alex and struck him with a baseball bat, causing serious injuries (broken ribs, head trauma).

**Charges against Alex**:
- Burglary
- Assault

**David's Defense**:
- Self-defense

**Key Questions**:
1. Did Alex unlawfully enter (burglary)?
2. Was David's use of force reasonable?
3. Was the force proportionate?
4. Did Alex attack David (disputed)?

### Case Data

- **8 Facts** (6 established, 2 disputed)
- **8 Evidence Items**:
  - E001: Broken window (physical)
  - E002: Footprints (physical)
  - E003: Baseball bat with blood (physical)
  - E004: Medical report (forensic)
  - E005: 911 call recording (digital)
  - E006: Neighbor testimony (testimonial)
  - E007: No defensive wounds on David (forensic)
  - E008: No weapon found on Alex (physical)

- **3 Witnesses**:
  - W001: David Thompson (victim/defendant in related charge)
  - W002: Margaret Foster (neighbor, neutral)
  - W003: Alex Johnson (defendant)

- **5 Applicable Laws**:
  - LAW_101: Assault
  - LAW_102: Aggravated Assault
  - LAW_104: Burglary
  - LAW_201: Self Defense
  - LAW_202: Excessive Defensive Force

## What to Explore Next

1. **Read the models**:
   ```bash
   # View domain models
   cat backend/app/domain/models.py
   ```

2. **Inspect legal rules**:
   ```bash
   # View principles
   cat backend/app/rules/data/principles.json

   # View criminal laws
   cat backend/app/rules/data/criminal_laws.json
   ```

3. **Study the test cases**:
   ```bash
   # See how models are tested
   cat backend/tests/test_domain/test_models.py

   # See how seed data is validated
   cat backend/tests/test_domain/test_seed_data.py
   ```

4. **Review architecture**:
   ```bash
   # Understand the system design
   cat ARCHITECTURE.md
   ```

## Using the Rule Engine

```python
from app.seed import get_case_by_id, get_case_001_bindings
from app.rules import ReferenceValidator, RuleEngine

case = get_case_by_id("CASE_001")
bindings = get_case_001_bindings()

# Nothing is evaluated before its references are verified
assert ReferenceValidator(case).validate_bindings(bindings).valid

evaluation = RuleEngine().evaluate_case(case, bindings)

for result in evaluation.rule_evaluations:
    print(f"{result.rule_id} [{result.subject}] -> {result.status.value}")
    for condition in result.conditions:
        print(f"   {condition.condition_id} {condition.status.value}: {condition.reasoning}")

print("Effects triggered:", evaluation.applied_effects)
print("Conflicts to address:", len(evaluation.conflicting_evidence))
```

See `README.md` for the weighting model and what CASE_001 evaluates to.

## Running the Judge Agent

```bash
cd backend
pip install -r requirements.txt

# See exactly what the judge is given - no API key, no model call
python -m app.cli judge CASE_001 --show-prompt

# Run it (reads LLM_PROVIDER and keys from .env, or pass --provider)
python -m app.cli judge CASE_001 --provider anthropic
python -m app.cli judge CASE_001 --provider local --model llama3.1
python -m app.cli judge CASE_001 --json > run.json
```

Every model call is appended to `logs/llm_interactions.jsonl`.

## Running the Full Court Procedure

```bash
pip install "langgraph>=1.2,<2"                 # the state machine
python -m app.cli court CASE_001 --show-graph   # print the procedure, no model call
python -m app.cli court CASE_001 --events       # run it, printing each stage live
```

## Running an Adversarial Trial

```bash
python -m app.cli trial CASE_001 --show-prompt   # the prosecution's opening prompt
python -m app.cli evidence CASE_001              # Evidence Agent only (1 call)
python -m app.cli trial CASE_001 --quick         # analysis, openings, closings, jury, judge (12 calls)
python -m app.cli trial CASE_001                 # the full trial (18 calls)
python -m app.cli trial CASE_001 --json > run.json   # save a run
python -m app.cli audit run.json --deterministic-only  # re-audit it, no model call
python -m app.cli trial CASE_001 --no-jury       # the Phase 5 trial (11 calls)
python -m app.cli trial CASE_001 --no-jury --no-evidence   # the Phase 4 trial (9 calls)
```

## Next Phases (Coming Soon)

### Phase 5+
- Evidence Agent
- Jury System
- Auditor
- Full LangGraph workflow
- FastAPI backend
- Next.js frontend

## Troubleshooting

### Tests Failing?

```bash
# Ensure you're in the backend directory
cd backend

# Ensure virtual environment is activated
# You should see (venv) in your prompt

# Reinstall dependencies
pip install -r requirements.txt

# Run tests again
pytest -v
```

### Import Errors?

Make sure you're running Python from the `backend` directory:
```bash
cd backend
python -m pytest tests/
```

### Need Help?

- Check `README.md` for detailed documentation
- Check `ARCHITECTURE.md` for system design
- Check `Promot.md` for original requirements

## Contributing

When implementing new phases:
1. Write tests first
2. Keep domain models pure (no LLM/database dependencies)
3. Maintain evidence grounding
4. Update documentation
5. Run all tests before committing

## Summary

**Phase 1-8 Status**: ✅ Complete and tested

You now have:
- Clean domain models
- Structured legal rules
- Complete test case (CASE_001)
- Comprehensive tests
- Solid foundation for multi-agent system

**Next Step**: Implement Phase 9 (FastAPI Backend).

---

Happy coding! 🎯
