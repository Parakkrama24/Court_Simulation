# Multi-Agent Legal Court Simulation System

## 1. Project Overview

Build a research-oriented multi-agent AI application that simulates a fictional legal court.

The purpose is to study how multiple specialized AI agents can collaboratively and adversarially reason about a legal case under a controlled set of laws, facts, evidence, witnesses, and court procedures.

This is NOT a real legal advice system and must not claim to provide legally valid judgments.

The application should initially use a completely fictional jurisdiction called:

**Republic of Arandia**

The first implementation should focus on fictional criminal cases.

The architecture must be designed so that the fictional legal system can later be replaced by real jurisdiction-specific legal sources without rewriting the entire application.

---

# 2. Main Research Idea

The system should simulate:

1. Case initialization
2. Fact and evidence analysis
3. Prosecution argument
4. Defense argument
5. Adversarial debate
6. Evidence verification
7. Judicial questioning
8. Independent jury deliberation
9. Judicial decision
10. Post-verdict legal/process audit

The key architectural principle is:

**Facts, Evidence, Laws, Arguments, and Decisions must remain separate entities.**

The LLM must reason over these entities but must not be allowed to arbitrarily modify the authoritative case state.

---

# 3. Initial Technology Stack

Use:

### Backend

* Python
* FastAPI
* LangGraph
* Pydantic
* SQLAlchemy
* PostgreSQL

### AI

Design an LLM abstraction layer so the provider can be changed.

Initially support an API-based LLM.

Do NOT hard-code the application to one model provider.

The architecture should allow:

* OpenAI-compatible APIs
* Anthropic-compatible APIs
* Local models later

### Frontend

Use:

* Next.js
* TypeScript
* Tailwind CSS

Build a visual courtroom simulation interface.

### Optional storage/search

Design an abstraction for a vector database.

Do not make vector search mandatory for the first MVP.

The first version should work entirely with structured fictional legal rules.

---

# 4. High-Level Architecture

Implement the following architecture:

```
                ┌──────────────────────┐
                │      Case Manager     │
                └──────────┬───────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
  Evidence Agent     Prosecution Agent   Defense Agent
         │                 │                 │
         └─────────────────┼─────────────────┘
                           ▼
                     Judge Agent
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
           Jury 1       Jury 2       Jury 3
              │            │            │
              └────────────┼────────────┘
                           ▼
                     Verdict Engine
                           │
                           ▼
                   Legal Process Auditor
```

Use LangGraph to represent the workflow and state transitions.

---

# 5. Agent Responsibilities

## 5.1 Case Manager Agent

Responsibilities:

* Initialize the case
* Load case facts
* Load evidence
* Load witnesses
* Identify potentially relevant legal rules
* Manage the court workflow
* Control which stage happens next

The Case Manager must not decide guilt or innocence.

---

## 5.2 Prosecution Agent

Objective:

Build the strongest evidence-supported prosecution case.

Responsibilities:

* Identify elements of alleged offenses
* Map evidence to legal elements
* Present arguments
* Challenge defense arguments
* Identify contradictions
* Respond to judicial questions
* Provide citations to case evidence and legal rules

Restrictions:

* Cannot invent facts
* Cannot invent evidence
* Cannot invent witnesses
* Cannot create new laws
* Cannot modify existing evidence
* Must distinguish facts from assumptions

---

## 5.3 Defense Agent

Objective:

Build the strongest evidence-supported defense.

Responsibilities:

* Challenge prosecution arguments
* Challenge evidence
* Identify reasonable doubt
* Present alternative interpretations
* Apply defenses such as self-defense where relevant
* Respond to judicial questions
* Identify weaknesses in prosecution reasoning

Restrictions:

Same evidence/fact restrictions as prosecution.

---

# 6. Evidence Agent

The Evidence Agent is neutral.

It should NOT advocate for prosecution or defense.

Responsibilities:

* Analyze evidence
* Determine which claims are directly supported
* Identify circumstantial evidence
* Identify contradictions
* Evaluate witness reliability according to predefined rules
* Detect unsupported claims
* Identify missing evidence
* Track evidence provenance

For every important claim, return:

* claim
* supporting evidence IDs
* contradicting evidence IDs
* confidence
* reasoning
* whether the claim is established, disputed, or unsupported

Example:

{
"claim": "Alex attacked David",
"supporting_evidence": ["E003", "W001"],
"contradicting_evidence": [],
"status": "supported"
}

---

# 7. Judge Agent

The Judge is the procedural authority.

Responsibilities:

* Control courtroom procedure
* Ask questions
* Identify missing reasoning
* Determine applicable laws
* Examine whether legal elements are supported
* Consider prosecution arguments
* Consider defense arguments
* Consider evidence analysis
* Produce a reasoned decision

The Judge must remain neutral.

The Judge must explicitly separate:

1. Established facts
2. Disputed facts
3. Applicable legal rules
4. Arguments
5. Analysis
6. Decision

The Judge must cite the relevant evidence IDs and legal rule IDs.

---

# 8. Jury Agents

Create multiple independent jury agents.

Initial MVP:

* Jury Agent 1
* Jury Agent 2
* Jury Agent 3

Each jury member independently evaluates the case.

Do not allow jury members to see other jury decisions before producing their initial decision.

Each jury agent should output:

* verdict
* reasoning
* evidence relied upon
* legal rules relied upon
* uncertainties
* confidence

After independent decisions, optionally perform a controlled deliberation phase.

---

# 9. Legal Process Auditor

Create a final auditor agent.

Its purpose is to inspect the simulation rather than decide the case.

Check:

### Evidence integrity

* Was evidence invented?
* Were evidence IDs valid?
* Were claims supported?

### Legal integrity

* Were only existing legal rules used?
* Were legal rules applied correctly?
* Were required legal elements considered?

### Reasoning integrity

* Did the agents contradict themselves?
* Did agents confuse assumptions with facts?
* Did the judge consider both sides?

### Procedural integrity

* Were all required courtroom stages completed?
* Did agents violate role restrictions?

Produce an audit report.

---

# 10. Legal Rule Engine

Do not store legal rules only as natural-language prompts.

Create structured legal rules.

Example:

{
"rule_id": "LAW_201",
"name": "Self Defense",
"category": "defense",
"conditions": [
{
"id": "C1",
"description": "Defendant reasonably believed they faced unlawful physical attack"
},
{
"id": "C2",
"description": "Force was necessary to protect the defendant"
},
{
"id": "C3",
"description": "Force was proportionate to the threat"
}
],
"effect": "self_defense_may_apply"
}

The rule engine should determine which conditions are satisfied based on structured facts/evidence.

LLMs may interpret evidence, but the authoritative legal rules remain outside the LLM.

---

# 11. Initial Legal Principles

Create the following fictional principles.

## P001 — Presumption of Innocence

A defendant is presumed innocent until the prosecution establishes the required elements of an offense according to the applicable standard.

## P002 — Burden of Proof

The prosecution carries the burden of establishing the required elements of the charged offense.

## P003 — Evidence Requirement

A claim cannot be treated as an established fact solely because an agent states it.

## P004 — Reasonable Doubt

If substantial uncertainty remains regarding an essential element of the offense, the defendant should not be convicted.

## P005 — Evidence Consistency

Contradictory evidence must be explicitly identified and considered.

---

# 12. Initial Criminal Laws

## LAW_101 — Assault

Required elements:

1. Intentional physical force
2. Physical contact
3. Unlawfulness

## LAW_102 — Aggravated Assault

Required elements:

1. Assault
2. Serious bodily injury

## LAW_103 — Theft

Required elements:

1. Intentional taking of property
2. Property belongs to another
3. Taking occurred without authorization
4. Intent to permanently deprive owner

## LAW_104 — Burglary

Required elements:

1. Unauthorized entry into a building
2. Intent to commit a criminal offense inside

## LAW_201 — Self Defense

Conditions:

1. Reasonable belief of unlawful physical attack
2. Force was necessary
3. Force was proportionate to the threat

## LAW_202 — Excessive Defensive Force

If defensive force substantially exceeds the immediate threat, self-defense protection may be reduced or rejected.

## LAW_301 — Attempt

Required elements:

1. Intent to commit an offense
2. Substantial step toward committing the offense
3. Offense was not completed

---

# 13. Evidence Rules

Implement:

### E001 — Direct Evidence

Direct evidence may establish a fact when sufficiently reliable.

### E002 — Circumstantial Evidence

Circumstantial evidence may support reasonable inference.

### E003 — Witness Reliability

Witness testimony can be challenged based on:

* contradiction
* memory limitations
* bias
* opportunity to observe
* personal interest

### E004 — Conflicting Evidence

Conflicting evidence must be explicitly identified.

### E005 — Fabricated Evidence

No agent may create evidence that is not present in the case database.

---

# 14. Court Procedure

Implement the following state machine:

CASE_INITIALIZATION

↓

EVIDENCE_ANALYSIS

↓

PROSECUTION_OPENING

↓

DEFENSE_OPENING

↓

PROSECUTION_ARGUMENT

↓

DEFENSE_ARGUMENT

↓

CROSS_EXAMINATION

↓

EVIDENCE_REVIEW

↓

JUDGE_QUESTIONS

↓

PROSECUTION_REBUTTAL

↓

DEFENSE_REBUTTAL

↓

CLOSING_ARGUMENTS

↓

JURY_INDEPENDENT_DELIBERATION

↓

JURY_DELIBERATION

↓

JUDGE_DECISION

↓

LEGAL_PROCESS_AUDIT

↓

CASE_COMPLETE

Use LangGraph conditional transitions where appropriate.

The Judge should be able to request additional analysis if an argument lacks evidence.

---

# 15. First Five Cases

Create seed data for these cases.

## CASE_001 — The Night Intruder

At 11:45 PM, Alex enters David's house without permission.

David confronts Alex.

Alex physically attacks David.

David strikes Alex with a metal object.

Alex suffers serious injuries.

Alex claims David committed aggravated assault.

David claims self-defense.

Relevant issues:

* burglary
* assault
* self-defense
* necessity
* proportionality
* excessive force

---

## CASE_002 — The Missing Laptop

A university laptop disappears.

Security footage shows Sarah entering the laboratory.

Sarah leaves carrying a bag.

The laptop is later found at Sarah's apartment.

Sarah claims she believed the laptop belonged to her.

The prosecution charges theft.

Main issue:

Whether the evidence establishes the required intent for theft.

---

## CASE_003 — The Broken Window

Tom sees a person breaking into his vehicle.

Tom throws a stone to stop the person.

The stone misses and breaks a nearby shop window.

The shop owner claims Tom committed property damage.

Tom claims he was attempting to stop a crime.

Main issue:

Conflict between defensive action and property damage.

---

## CASE_004 — The Witness Problem

A robbery occurs outside a restaurant.

Witness A says the attacker wore a red jacket.

Witness B says the attacker wore a black jacket.

Security footage is unclear.

Five minutes later police find John nearby wearing a red jacket.

Witness A identifies John.

Later investigators discover Witness A was intoxicated.

John denies involvement.

Main issues:

* witness reliability
* conflicting evidence
* circumstantial evidence
* identification

---

## CASE_005 — The Perfect Alibi

Michael is accused of stealing $50,000.

Prosecution evidence:

* CCTV
* fingerprint evidence
* witness testimony
* financial records

Defense evidence:

* restaurant receipt
* phone location
* two witnesses

One defense witness is Michael's business partner.

Investigators later discover the phone location may have been spoofed.

Main issues:

* credibility
* evidence reliability
* conflicting evidence
* reasonable doubt

---

# 16. Data Models

Create Pydantic models and database models for:

## Case

Fields:

* case_id
* title
* description
* jurisdiction
* case_type
* defendant
* prosecution
* facts
* evidence
* witnesses
* charges
* applicable_laws
* procedure
* status

## Fact

Fields:

* fact_id
* description
* source
* status

Status:

* established
* disputed
* unknown

## Evidence

Fields:

* evidence_id
* type
* description
* source
* supports
* contradicts
* reliability
* metadata

## Witness

Fields:

* witness_id
* name
* statement
* reliability_factors
* related_evidence

## LegalRule

Fields:

* rule_id
* name
* category
* description
* conditions
* effect
* jurisdiction

## Argument

Fields:

* argument_id
* agent_id
* claim
* evidence_ids
* law_ids
* counter_argument_ids
* reasoning
* confidence

## Verdict

Fields:

* verdict_id
* case_id
* charges
* decision
* reasoning
* evidence_used
* laws_used
* unresolved_questions
* confidence

## AuditReport

Fields:

* audit_id
* case_id
* evidence_violations
* legal_violations
* procedural_violations
* reasoning_issues
* hallucinations
* final_assessment

---

# 17. LangGraph State

Create a strongly typed CourtState.

It should contain at minimum:

* case
* current_stage
* facts
* evidence
* applicable_laws
* prosecution_arguments
* defense_arguments
* evidence_analysis
* judge_questions
* jury_decisions
* judge_decision
* audit_report
* event_history

Every important agent action should be recorded in event_history.

---

# 18. Agent Communication

Do not allow agents to communicate through uncontrolled free-form global chat.

Instead, use structured messages.

Example:

{
"sender": "prosecution_agent",
"recipient": "judge_agent",
"message_type": "argument",
"claim": "...",
"evidence_ids": ["E001", "E003"],
"law_ids": ["LAW_101"],
"reasoning": "..."
}

This makes the system observable and testable.

---

# 19. Prevent Hallucination

Implement validation before accepting agent output.

For every:

* evidence ID
* fact ID
* witness ID
* law ID

verify that it exists.

If an agent references a nonexistent ID:

1. Reject the message
2. Log the violation
3. Ask the agent to regenerate using valid references

Never silently accept fabricated references.

---

# 20. Frontend

Create a visual courtroom dashboard.

Main screen:

```text
┌──────────────────────────────────────────────┐
│             CASE: Night Intruder             │
├──────────────────────────────────────────────┤
│                                              │
│  PROSECUTION          JUDGE          DEFENSE │
│      🧑‍⚖️                 ⚖️               🧑‍⚖️ │
│                                              │
├──────────────────────────────────────────────┤
│              COURTROOM TIMELINE              │
│                                              │
│ Evidence Analysis                            │
│        ↓                                     │
│ Prosecution Argument                         │
│        ↓                                     │
│ Defense Argument                             │
│        ↓                                     │
│ Judge Questions                              │
│        ↓                                     │
│ Jury Deliberation                            │
│        ↓                                     │
│ Verdict                                      │
└──────────────────────────────────────────────┘
```

Provide pages/components for:

### Case Selection

Show available cases.

### Case Details

Show:

* Facts
* Charges
* Evidence
* Witnesses
* Laws

### Live Simulation

Display agent activity as it happens.

### Evidence Panel

Show:

* evidence
* supporting claims
* contradicting claims
* reliability

### Legal Rules Panel

Show the laws referenced by agents.

### Debate Panel

Display prosecution and defense arguments.

### Jury Panel

Show independent jury decisions.

### Judge Decision

Show:

* findings
* applicable law
* reasoning
* verdict

### Audit Panel

Show:

* hallucinations
* unsupported claims
* procedural violations
* evidence violations

---

# 21. Streaming

The frontend should receive simulation events in real time.

Use WebSocket or Server-Sent Events.

Events should include:

* AGENT_STARTED
* AGENT_ARGUMENT
* EVIDENCE_ANALYZED
* JUDGE_QUESTION
* AGENT_RESPONSE
* JURY_DECISION
* JUDGE_DECISION
* AUDIT_COMPLETED

The UI should visually update as the simulation progresses.

---

# 22. Logging and Observability

Every LLM interaction must be logged.

Store:

* agent
* prompt version
* model
* timestamp
* input state
* output
* token usage if available
* latency
* validation result

Do not expose hidden chain-of-thought.

Store concise structured reasoning/rationales intended for application-level explanation instead.

---

# 23. Evaluation Framework

Build the project so we can later evaluate:

### Legal rule accuracy

Did the agent identify the correct rule?

### Evidence grounding

Did the agent use actual evidence?

### Hallucination rate

How often did agents invent facts/evidence/laws?

### Argument consistency

Did agents contradict their own earlier claims?

### Verdict agreement

How often do independent jury members agree?

### Process compliance

Did agents follow the court procedure?

### Reasoning quality

Does the final decision logically connect:

FACTS → EVIDENCE → LAW → ANALYSIS → DECISION?

Create an evaluation module so these metrics can be measured automatically.

---

# 24. Important Safety/Scope Requirements

This is a fictional legal simulation.

The UI must clearly state:

"Research simulation only. This system does not provide legal advice or determine real legal rights or obligations."

Do not use real people's private information.

Do not initially claim that the system can predict real court outcomes.

Do not present the system as a replacement for lawyers or judges.

---

# 25. Development Strategy

Do NOT implement everything at once.

Build incrementally.

## Phase 1 — Domain model

Implement:

* Case
* Fact
* Evidence
* Witness
* LegalRule
* Argument
* Verdict

Create seed data.

No LLM yet.

---

## Phase 2 — Rule engine

Implement deterministic legal-rule evaluation.

Test:

Facts + Evidence → Rule Conditions → Applicable conclusions.

---

## Phase 3 — Single agent

Implement only:

Case → Judge Agent → Decision

This validates the basic LLM integration.

---

## Phase 4 — Two-agent adversarial system

Implement:

Prosecution ↔ Defense → Judge

---

## Phase 5 — Evidence Agent

Add neutral evidence analysis.

---

## Phase 6 — Jury

Add three independent jury agents.

---

## Phase 7 — Auditor

Add the Legal Process Auditor.

---

## Phase 8 — Frontend visualization

Build the courtroom UI.

---

## Phase 9 — Streaming

Add real-time simulation events.

---

## Phase 10 — Evaluation

Implement automated evaluation metrics and experiment tracking.

---

# 26. Engineering Requirements

Use clean architecture.

Separate:

* domain
* agents
* workflow
* legal rules
* LLM providers
* database
* API
* frontend

Use environment variables for secrets.

Provide `.env.example`.

Use Docker Compose for:

* backend
* frontend
* PostgreSQL

Provide:

* README
* architecture documentation
* API documentation
* setup instructions
* testing instructions

Write unit tests for the legal rule engine.

Write integration tests for the LangGraph workflow.

Do not create unnecessary abstractions before they are needed.

Prefer simple, readable implementations.

---

# 27. First Development Task

Before writing the full implementation:

1. Analyze the requirements.
2. Propose the project directory structure.
3. Explain the architecture.
4. Define the domain models.
5. Define the LangGraph state.
6. Define the initial workflow.
7. Identify risks and ambiguities.
8. Create a phased implementation plan.

Then implement **Phase 1 only**.

Do not jump directly to implementing all agents.

After Phase 1 is complete, run tests and verify the domain model before continuing.

The system should be designed as a research platform where we can experiment with different agent configurations later.

Do not optimize for complexity. Optimize for:

**observability + controllability + reproducibility + evidence grounding + modularity.**
