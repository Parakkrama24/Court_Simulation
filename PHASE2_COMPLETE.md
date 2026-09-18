# Phase 2 Implementation Complete ✅

## Overview

**Phase 2: Legal Rule Engine** has been implemented and tested.

**Completion Date**: 2026-09-17
**Status**: ✅ All tests passing (143/143)
**Next Phase**: Phase 3 - Single Agent (Case → Judge Agent → Decision)

The engine evaluates structured legal rules against a case record with no LLM
involved. Given the same case and the same bindings it always produces the same
conclusions, which is what makes later agent behaviour measurable.

```
Facts + Evidence --(element bindings)--> Conditions --> Rule status --> Effects
```

---

## What Was Built

### 1. Element Bindings (the missing link)

**Location**: `backend/app/domain/models.py`, `backend/app/seed/element_bindings.py`

Legal conditions are natural-language ("Force was proportionate to the
threat"). Something has to say *which* facts and evidence bear on that element.
That is an `ElementBinding`:

```python
ElementBinding(
    binding_id="B015",
    case_id="CASE_001",
    rule_id="LAW_201",
    condition_id="C3",
    subject="David Thompson",
    stance=BindingStance.CONTRADICTS,
    fact_ids=["F006", "F008"],
    evidence_ids=["E004", "E008"],
    note="Repeated blows with a metal bat against an unarmed person",
)
```

**Key design point**: a binding states only *what bears on* an element - never
whether the element holds. That conclusion is the engine's, and the engine
alone. In Phase 5 an Evidence Agent may propose bindings; the validator will
check the IDs and the engine will still compute the outcome.

**Why `subject`**: CASE_001 involves conduct by two parties, so LAW_101 must be
evaluated separately for the charge against Alex Johnson and for David
Thompson's use of force. Bindings and evaluations are therefore per-party.

18 bindings were authored for CASE_001 from the case file, covering LAW_101,
LAW_102, LAW_104, LAW_201, and LAW_202.

### 2. Legal Rule Registry

**Location**: `backend/app/rules/registry.py`

Indexed, read-only access to the 17 seeded rules: lookup by ID, by category,
and by condition, with duplicate rule IDs rejected at construction. The
registry is the single authority on what rules exist - agents can reference
rules but can never add to this set.

### 3. Condition Evaluator

**Location**: `backend/app/rules/evaluator.py`

Turns bound material into one of four condition statuses.

**Weighting**:
- Fact weight by status: established 1.0, disputed 0.5, unknown 0.25
- Evidence weight: `reliability × type factor`, where physical, forensic,
  digital, and documentary evidence score 1.0, testimonial 0.85, and
  circumstantial 0.7
- A condition's strength on each side is its *strongest single* reference -
  stacking weak duplicates never manufactures certainty

**Status**:

| Support ≥ 0.6 | Contradiction ≥ 0.4 | Status |
|---|---|---|
| yes | no  | `satisfied` |
| yes | yes | `disputed` |
| no  | yes | `unsatisfied` |
| no  | no  | `unsupported` |

Every result carries the per-reference weight breakdown and a written
explanation, so the chain from evidence to conclusion is inspectable.

**Witness reliability (rule E003)** also lives here: declared reliability
factors are scored deterministically into a 0-1 score plus explicit challenge
grounds (bias, memory limitations, inconsistency, opportunity to observe,
personal interest). Unrecognised factors are reported as unscored rather than
silently ignored.

### 4. Rule Engine

**Location**: `backend/app/rules/engine.py`

- `evaluate_rule(case, rule_id, subject, bindings)` → one `RuleEvaluation`
- `evaluate_case(case, bindings)` → every applicable law per party, plus the
  case-wide principles, witness assessments, conflicts, and the policy used
- `detect_conflicts(case, evaluations)` → evidence rule E004 reporting

**Rule status**: `satisfied` when every required condition is satisfied,
`not_satisfied` when any required condition is contradicted, `indeterminate`
while a required condition remains disputed or unsupported, and
`unconditional` for rules that state no conditions (the principles). An effect
is triggered only by `satisfied` or `unconditional`.

**Rule dependencies**: a condition may declare `depends_on_rule`, so LAW_102's
"Assault" element is resolved by evaluating LAW_101 for the same subject rather
than by re-proving assault. Derived conditions inherit the underlying
references, take the weakest required support and the strongest contradiction
of the rule they depend on, and cycles are detected, reported in condition
metadata, and carried up the chain instead of recursing forever.

### 5. Reference Validator

**Location**: `backend/app/rules/validator.py`

The gate that keeps agent output grounded. Validates arguments, verdicts, and
bindings: every evidence, fact, witness, law, condition, and counter-argument
ID must exist. Results carry regeneration-ready messages and convert to
audit-report-shaped violation records via `as_violations()`, ready for the
Legal Process Auditor in Phase 7.

### 6. Evaluation Policy

**Location**: `backend/app/rules/models.py`

Thresholds and weights are data (`EvaluationPolicy`), not constants buried in
logic, and the policy used is recorded in every `CaseEvaluation`. Experiments
can vary how strictly disputed facts or low-reliability evidence are treated
without touching the evaluation code.

---

## CASE_001 Under the Engine

| Rule | Subject | Status | Why |
|---|---|---|---|
| LAW_104 Burglary | Alex Johnson | indeterminate | Entry established (F001, F002, E001, E002); **no evidence at all** speaks to intent to commit an offence inside |
| LAW_101 Assault | Alex Johnson | not_satisfied | The alleged attack rests on disputed F004 (0.50) and testimonial E006 (0.595), both below threshold, and is contradicted by E007 (0.85) |
| LAW_101 Assault | David Thompson | indeterminate | Force and contact established via E003/E004; unlawfulness disputed by F004 |
| LAW_102 Aggravated Assault | David Thompson | indeterminate | Serious injury established (E004); the assault element is inherited from LAW_101 |
| LAW_201 Self Defense | David Thompson | not_satisfied | Reasonable belief established (E005 and the break-in), but necessity and proportionality are contradicted by E008 and E004 |
| LAW_202 Excessive Force | David Thompson | indeterminate | Force used is established; whether it substantially exceeded the threat is contested |
| P001–P005 | case-wide | unconditional | Principles apply to every criminal case |

**Witness reliability**: Margaret Foster 0.95 (no challenge grounds), David
Thompson 0.65 (bias, high personal interest), Alex Johnson 0.15 (bias, possible
memory impairment, conflict with other evidence, very high personal interest).

**No offense or defense effect is triggered on this record.** The engine reports
open questions rather than resolving them - the two elements that would decide
the case (Alex's intent, and whether Alex attacked first) have no evidence and
contested evidence respectively. Those are precisely the questions the
adversarial agent phases exist to argue about.

---

## Files

**Created**:
```
backend/app/rules/
├── __init__.py               # Public API of the rules package
├── models.py                 # Statuses, results, EvaluationPolicy
├── registry.py               # LegalRuleRegistry
├── evaluator.py              # ConditionEvaluator, witness reliability
├── engine.py                 # RuleEngine
└── validator.py              # ReferenceValidator

backend/app/seed/element_bindings.py   # CASE_001 bindings

backend/tests/test_rules/
├── __init__.py
├── conftest.py                     # Synthetic case + synthetic rule set
├── test_registry.py                # 13 tests
├── test_evaluator.py               # 20 tests
├── test_engine.py                  # 27 tests
├── test_validator.py               # 17 tests
└── test_case_001_evaluation.py     # 28 tests
```

**Modified**:
- `backend/app/domain/models.py` - added `ElementBinding`, `BindingStance`, and
  `Condition.depends_on_rule`; migrated `class Config` to `ConfigDict` and
  `datetime.utcnow` to a timezone-aware `utc_now()` (the two deprecation
  warnings flagged at the end of Phase 1)
- `backend/app/domain/__init__.py`, `backend/app/seed/__init__.py` - exports
- `backend/app/rules/data/criminal_laws.json` - LAW_102 C1 now declares
  `depends_on_rule: LAW_101`

---

## Tests

```
143 passed ✅ (38 from Phase 1, 105 new)
Execution time: ~0.4 seconds
```

Engine tests run against a **synthetic** case and rule set defined in
`conftest.py`, so editing CASE_001 cannot silently change what they assert.
`test_case_001_evaluation.py` is the separate end-to-end net that pins what the
real seeded record evaluates to.

Covered: weight derivation, all four condition statuses, threshold boundaries,
policy overrides, deduplication, unknown references, every rule status,
optional-only rules, per-subject isolation, rule dependencies (satisfied,
failed, indeterminate, missing, circular), case-level evaluation, cross-case
binding isolation, conflict detection, witness scoring (including clamping),
and validation of arguments, verdicts, and bindings.

**Reproducibility** is asserted directly: evaluating the same case twice
produces identical `model_dump()` output.

---

## Design Decisions

### 1. Bindings are input, not inference

The engine could have tried to match condition text to fact text. It does not.
Matching natural language is exactly the step that later needs an LLM, and
mixing it into the engine would make the authoritative layer non-deterministic.
Instead the mapping is explicit data the engine consumes, so an agent can
propose it and be audited on it.

### 2. Strength is `max`, not a sum

Summing weights would let three weak, unreliable items outweigh one forensic
report, and would let an agent manufacture certainty by citing the same thing
in several ways. The strongest single reference decides.

### 3. `indeterminate` is a first-class outcome

Real cases turn on elements nobody has evidence for. Collapsing "unsupported"
into "not satisfied" would hide the difference between *disproved* and *never
addressed* - the distinction the prosecution's burden (P002) and reasonable
doubt (P004) both rest on.

### 4. Per-subject evaluation

CASE_001 has two parties whose conduct is at issue under the same assault rule.
Without a subject, the engine would silently merge David's blows with Alex's
alleged attack. Bindings therefore carry the party, and rules are evaluated per
party.

### 5. Evidence rules E003/E004 are code; E001/E002/E005 are constraints

Witness reliability and conflict detection are computable, so they are
implemented. Direct vs circumstantial weighting (E001/E002) is expressed in the
policy's type factors. E005 (no fabricated evidence) is enforced by the
validator rather than evaluated as a rule.

---

## What This Enables

Phase 3 can now hand a Judge Agent a case *plus* a deterministic evaluation of
which legal elements hold, which are contested, and which have no evidence -
and can check the agent's output against the engine's own conclusions. The
validator is already in place to reject any fabricated reference the agent
produces.

---

## Known Limitations

1. **Bindings are hand-authored.** Only CASE_001 has them; CASE_002–005 are not
   yet seeded (Phase 1 seeded one case).
2. **Thresholds are judgement calls.** 0.6 and 0.4 are defensible defaults, not
   findings. They are policy data precisely so they can be varied and studied.
3. **No persistence.** Evaluations are computed in memory; storing them is a
   database-phase concern.
4. **Conflict detection is structural.** It reports contested elements and
   contradicting evidence relationships, not semantic contradictions between
   two witness statements - that needs the Evidence Agent.

---

**Phase 2 Completion Date**: 2026-09-17
**Next Milestone**: Phase 3 - Single Agent
**Overall Progress**: 2/12 phases complete (16.7%)

**Research Simulation Only**: This system does not provide legal advice or
determine real legal rights or obligations.
