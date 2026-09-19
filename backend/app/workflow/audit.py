"""LEGAL_PROCESS_AUDIT: inspect how a trial ran

``audit_trial`` audits a finished ``TrialRun``, whether it is fresh from
``run_adversarial_trial`` or loaded back from a saved JSON run. It always runs
the deterministic checks below; given a provider, it also runs the Legal
Process Auditor agent for what code cannot judge. Both feed one ``AuditReport``.

Deterministic checks, by spec section 9 area:

- Evidence integrity - every invented ID an agent tried to cite and was
  caught (from rejected attempts); a re-check of every accepted output's IDs;
  arguments the Evidence Agent found unsupported.
- Legal integrity - the judge going beyond the rule engine; a defense rule
  argued for a party it does not concern.
- Reasoning integrity - assumptions presented as facts; the judge or a juror
  not weighing both sides; judge and jury disagreeing; votes changed in
  deliberation.
- Procedural integrity - spec section 14 stages not completed; a message sent
  by an agent not allowed to speak at that stage; the Evidence Agent breaching
  neutrality; repeated rejections.
"""

import re
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Set, Tuple

from app.agents.advocate import STAGE_SPEAKERS, AdvocateRole
from app.agents.auditor import (
    AUDITOR_AGENT_ID,
    AuditCategory,
    AuditFinding,
    AuditorAgent,
    FindingSource,
    ProcessAudit,
    Severity,
    build_audit_report,
)
from app.agents.base import AgentAttempt
from app.agents.evidence import EVIDENCE_AGENT_ID, ArgumentSupport, evidence_context
from app.agents.jury import jury_context
from app.agents.record import render_argument, render_case_record
from app.domain import CourtStage, LegalCategory
from app.llm import InteractionLog, LLMProvider
from app.rules import LegalRuleRegistry, ReferenceValidator

if TYPE_CHECKING:  # imported for typing only; the runner imports this module
    from .adversarial import TrialRun

JUDGE_AGENT_ID = "judge_agent"

# Stages of spec section 14 this simulation does not implement yet.
NOT_IMPLEMENTED = {CourtStage.CROSS_EXAMINATION, CourtStage.JUDGE_QUESTIONS}

# Validation messages that mean an agent tried to cite something that does not exist.
_HALLUCINATION_MARKERS = (
    re.compile(r"Unknown \w+ reference"),
    re.compile(r"has not been presented"),
    re.compile(r"has no condition"),
    re.compile(r"is not (a|one of the) charges?"),
    re.compile(r"unknown reference"),
)
_QUOTED = re.compile(r"'([^']+)'")


class _Findings:
    """Collects deterministic findings with sequential IDs"""

    def __init__(self) -> None:
        self.items: List[AuditFinding] = []

    def add(
        self,
        category: AuditCategory,
        severity: Severity,
        check: str,
        description: str,
        agent_id: str = "",
        stage: str = "",
        references: Iterable[str] = (),
    ) -> None:
        self.items.append(
            AuditFinding(
                finding_id=f"AUD-D-{len(self.items) + 1:03d}",
                category=category,
                severity=severity,
                check=check,
                agent_id=agent_id,
                stage=stage,
                description=description,
                references=list(dict.fromkeys(references)),
                source=FindingSource.DETERMINISTIC,
            )
        )


def _artifacts(run: "TrialRun") -> List[Tuple[str, str, List[AgentAttempt]]]:
    """(agent, stage, attempts) for every agent task in the run"""
    items: List[Tuple[str, str, List[AgentAttempt]]] = []
    if run.evidence_analysis is not None:
        items.append((EVIDENCE_AGENT_ID, "EVIDENCE_ANALYSIS", run.evidence_analysis.attempts))
    for review in run.evidence_reviews:
        items.append((EVIDENCE_AGENT_ID, "EVIDENCE_REVIEW", review.attempts))
    for turn in run.turns:
        items.append((turn.agent_id, turn.stage.value, turn.attempts))
    for decision in run.jury_independent + run.jury_deliberation:
        items.append((decision.juror_id, decision.stage.value, decision.attempts))
    items.append((JUDGE_AGENT_ID, "JUDGE_DECISION", run.judgment.attempts))
    return items


# ============================================================================
# Evidence integrity
# ============================================================================


def _check_caught_hallucinations(run: "TrialRun", out: _Findings) -> None:
    for agent_id, stage, attempts in _artifacts(run):
        for attempt in attempts:
            if attempt.accepted:
                continue
            for error in attempt.errors:
                if any(marker.search(error) for marker in _HALLUCINATION_MARKERS):
                    out.add(
                        AuditCategory.HALLUCINATION,
                        Severity.MINOR,
                        "caught_hallucination",
                        f"Attempt {attempt.attempt} was rejected and regenerated: {error}",
                        agent_id,
                        stage,
                        _QUOTED.findall(error)[:3],
                    )


def _check_accepted_references(
    run: "TrialRun", registry: LegalRuleRegistry, out: _Findings
) -> None:
    """Defense in depth: re-validate every accepted output's citations"""
    validator = ReferenceValidator(run.case, registry)
    argument_ids = [a.argument_id for a in run.arguments]
    problems: List[Tuple[str, str, List[str]]] = []

    for turn in run.turns:
        for argument in turn.arguments:
            result = validator.validate_argument(argument, argument_ids)
            problems.append((turn.agent_id, turn.stage.value, result.messages))
    verdicts = [(JUDGE_AGENT_ID, "JUDGE_DECISION", run.judgment.verdict)]
    verdicts += [(d.juror_id, d.stage.value, d.verdict) for d in run.jury_independent]
    verdicts += [(d.juror_id, d.stage.value, d.verdict) for d in run.jury_deliberation]
    for agent_id, stage, verdict in verdicts:
        problems.append((agent_id, stage, validator.validate_verdict(verdict).messages))
    if run.evidence_analysis is not None:
        output = run.evidence_analysis.output
        evidence = [e.evidence_id for e in output.evidence]
        for claim in output.claims:
            evidence += claim.supporting_evidence_ids + claim.contradicting_evidence_ids
        result = validator.validate_references(
            evidence_ids=list(dict.fromkeys(evidence)),
            witness_ids=[w.witness_id for w in output.witnesses],
            location="evidence analysis",
        )
        problems.append((EVIDENCE_AGENT_ID, "EVIDENCE_ANALYSIS", result.messages))

    for agent_id, stage, messages in problems:
        for message in messages:
            out.add(
                AuditCategory.HALLUCINATION,
                Severity.CRITICAL,
                "accepted_with_invalid_reference",
                f"Accepted output contains an invalid reference: {message}",
                agent_id,
                stage,
                _QUOTED.findall(message)[:3],
            )


def _check_argument_support(run: "TrialRun", out: _Findings) -> None:
    owner = {a.argument_id: a.agent_id for a in run.arguments}
    for review in run.evidence_reviews:
        for item in review.output.reviews:
            if item.support == ArgumentSupport.SUPPORTED:
                continue
            unsupported = item.support == ArgumentSupport.UNSUPPORTED
            out.add(
                AuditCategory.EVIDENCE,
                Severity.MINOR if unsupported else Severity.INFO,
                "unsupported_argument" if unsupported else "partially_supported_argument",
                f"The Evidence Agent found {item.argument_id} {item.support.value}: "
                + "; ".join(item.issues),
                owner.get(item.argument_id, ""),
                "EVIDENCE_REVIEW",
                [item.argument_id],
            )

    flags = []
    if run.evidence_analysis is not None:
        flags += [(f, "EVIDENCE_ANALYSIS") for f in run.evidence_analysis.flags]
    for review in run.evidence_reviews:
        flags += [(f, "EVIDENCE_REVIEW") for f in review.flags]
    for flag, stage in flags:
        if flag.kind == "neutrality":
            out.add(
                AuditCategory.PROCEDURAL,
                Severity.MAJOR,
                "evidence_agent_neutrality",
                f"The neutral Evidence Agent used outcome language: {flag.detail}",
                EVIDENCE_AGENT_ID,
                stage,
            )
        else:
            out.add(
                AuditCategory.EVIDENCE,
                Severity.INFO,
                flag.kind,
                flag.detail,
                EVIDENCE_AGENT_ID,
                stage,
            )


# ============================================================================
# Legal integrity
# ============================================================================


def _check_engine_divergence(run: "TrialRun", out: _Findings) -> None:
    for d in run.judgment.divergences:
        where = " ".join(x for x in (d.charge, d.rule_id, d.condition_id) if x)
        out.add(
            AuditCategory.LEGAL,
            Severity.MAJOR if d.against_defendant else Severity.INFO,
            f"judge_{d.kind}",
            f"Judge departed from the rule engine on {where or 'the record'}: "
            f"judge={d.judge_view}, engine={d.engine_view}"
            + (" (against the defendant)" if d.against_defendant else " (for the defendant)"),
            JUDGE_AGENT_ID,
            "JUDGE_DECISION",
            [x for x in (d.rule_id,) if x],
        )


def _check_defense_rule_party(
    run: "TrialRun", registry: LegalRuleRegistry, out: _Findings
) -> None:
    """A defense rule argued by the defense for a party it does not concern"""
    defendant = run.case.defendant
    for argument in run.arguments:
        if argument.agent_id != AdvocateRole.DEFENSE.agent_id:
            continue
        for rule_id in argument.law_ids:
            rule = registry.get(rule_id)
            if rule is None or rule.category != LegalCategory.DEFENSE:
                continue
            subjects = {e.subject for e in run.evaluation.for_rule(rule_id)}
            if subjects and defendant not in subjects:
                out.add(
                    AuditCategory.LEGAL,
                    Severity.MINOR,
                    "defense_rule_other_party",
                    f"{argument.argument_id} invokes {rule_id} ({rule.name}), which in this "
                    f"record concerns {', '.join(sorted(subjects))}, not the defendant "
                    f"{defendant}.",
                    argument.agent_id,
                    str(argument.metadata.get("stage", "")),
                    [argument.argument_id, rule_id],
                )


# ============================================================================
# Reasoning integrity
# ============================================================================


def _check_assumptions(run: "TrialRun", out: _Findings) -> None:
    for turn in run.turns:
        for flag in turn.flags:
            argument = turn.arguments[flag.argument_index - 1]
            out.add(
                AuditCategory.REASONING,
                Severity.MINOR,
                "assumption_presented_as_fact",
                f"{argument.argument_id}: {flag.detail}",
                turn.agent_id,
                turn.stage.value,
                [argument.argument_id],
            )


def _check_both_sides(run: "TrialRun", out: _Findings) -> None:
    by_party: Dict[str, Set[str]] = {}
    for argument in run.arguments:
        by_party.setdefault(argument.agent_id, set()).add(argument.argument_id)
    deciders = [
        (JUDGE_AGENT_ID, "JUDGE_DECISION", run.judgment.decision.arguments_considered)
    ]
    deciders += [
        (d.juror_id, d.stage.value, d.output.arguments_considered)
        for d in run.jury_independent + run.jury_deliberation
    ]
    for agent_id, stage, considered in deciders:
        for party, ids in by_party.items():
            if not ids.intersection(considered):
                out.add(
                    AuditCategory.REASONING,
                    Severity.MAJOR,
                    "one_side_ignored",
                    f"{agent_id} considered no argument from {party}.",
                    agent_id,
                    stage,
                )


def _check_jury(run: "TrialRun", out: _Findings) -> None:
    if run.jury_result is None:
        return
    for row in run.judge_jury_agreement:
        if row["agrees"]:
            continue
        hung = row["jury"] == "hung"
        out.add(
            AuditCategory.REASONING,
            Severity.INFO if hung else Severity.MINOR,
            "judge_jury_disagreement",
            f"On {row['charge']} the judge decided {row['judge']}; the jury's verdict was "
            f"{row['jury']}." + ("" if hung else " The judge's analysis should explain why."),
            JUDGE_AGENT_ID,
            "JUDGE_DECISION",
        )
    for change in run.jury_result.vote_changes:
        out.add(
            AuditCategory.REASONING,
            Severity.INFO,
            "vote_changed_in_deliberation",
            f"{change.juror_id} changed from {change.before.value} to {change.after.value} "
            f"on {change.charge} in deliberation.",
            change.juror_id,
            "JURY_DELIBERATION",
        )


# ============================================================================
# Procedural integrity
# ============================================================================


def _allowed_senders(stage: CourtStage) -> Optional[Set[str]]:
    if stage in STAGE_SPEAKERS:
        return {role.agent_id for role in STAGE_SPEAKERS[stage]}
    if stage in (CourtStage.EVIDENCE_ANALYSIS, CourtStage.EVIDENCE_REVIEW):
        return {EVIDENCE_AGENT_ID}
    if stage == CourtStage.JUDGE_DECISION:
        return {JUDGE_AGENT_ID}
    if stage == CourtStage.LEGAL_PROCESS_AUDIT:
        return {AUDITOR_AGENT_ID}
    return None  # jury stages are checked by prefix


def _check_roles(run: "TrialRun", out: _Findings) -> None:
    for message in run.messages:
        if message.stage in (
            CourtStage.JURY_INDEPENDENT_DELIBERATION,
            CourtStage.JURY_DELIBERATION,
        ):
            allowed = message.sender.startswith("jury_")
        else:
            senders = _allowed_senders(message.stage)
            allowed = senders is None or message.sender in senders
        if not allowed:
            out.add(
                AuditCategory.PROCEDURAL,
                Severity.MAJOR,
                "role_violation",
                f"{message.sender} sent {message.message_id} at {message.stage.value}, a "
                "stage where it has no role.",
                message.sender,
                message.stage.value,
                [message.message_id],
            )


def _check_stages(run: "TrialRun", out: _Findings) -> None:
    seen = {e["stage"] for e in run.event_history}
    for stage in CourtStage:
        if stage in (CourtStage.LEGAL_PROCESS_AUDIT, CourtStage.CASE_COMPLETE):
            continue  # this audit is itself the LEGAL_PROCESS_AUDIT stage
        if stage.value in seen:
            continue
        if stage in NOT_IMPLEMENTED:
            out.add(
                AuditCategory.PROCEDURAL,
                Severity.INFO,
                "stage_not_implemented",
                f"{stage.value} is part of the specified court procedure but is not yet "
                "implemented in this simulation.",
                stage=stage.value,
            )
        else:
            out.add(
                AuditCategory.PROCEDURAL,
                Severity.INFO,
                "stage_skipped",
                f"{stage.value} did not take place; it was left out of this run's "
                "configuration.",
                stage=stage.value,
            )


def _check_rejections(run: "TrialRun", out: _Findings) -> None:
    for agent_id, stage, attempts in _artifacts(run):
        rejected = sum(1 for a in attempts if not a.accepted)
        if rejected >= 2:
            out.add(
                AuditCategory.PROCEDURAL,
                Severity.INFO,
                "repeated_rejections",
                f"{agent_id} needed {rejected + 1} attempts at {stage}.",
                agent_id,
                stage,
            )


# ============================================================================
# Entry point
# ============================================================================


def deterministic_findings(
    run: "TrialRun", registry: Optional[LegalRuleRegistry] = None
) -> List[AuditFinding]:
    """Every deterministic check over a finished trial"""
    registry = registry or LegalRuleRegistry()
    out = _Findings()
    _check_caught_hallucinations(run, out)
    _check_accepted_references(run, registry, out)
    _check_argument_support(run, out)
    _check_engine_divergence(run, out)
    _check_defense_rule_party(run, registry, out)
    _check_assumptions(run, out)
    _check_both_sides(run, out)
    _check_jury(run, out)
    _check_roles(run, out)
    _check_stages(run, out)
    _check_rejections(run, out)
    return out.items


def build_dossier(run: "TrialRun", registry: LegalRuleRegistry) -> Dict[str, Any]:
    """Everything the auditor agent reviews, as plain data"""
    record = render_case_record(
        run.case,
        run.evaluation,
        registry,
        run.arguments,
        evidence_context(run.evidence_analysis, run.evidence_reviews),
        jury_context(run.jury_result) if run.jury_result else None,
    )
    record["party_arguments"] = [render_argument(a) for a in run.arguments]
    record["transcript"] = [
        {
            "message_id": m.message_id,
            "stage": m.stage.value,
            "sender": m.sender,
            "type": m.message_type.value,
            "claim": m.claim,
            "argument_ids": m.argument_ids,
        }
        for m in run.messages
    ]
    record["jury_decisions"] = [
        {
            "juror_id": d.juror_id,
            "stage": d.stage.value,
            "decision": d.output.model_dump(mode="json"),
            "changed_charges": d.changed_charges,
        }
        for d in run.jury_independent + run.jury_deliberation
    ]
    record["judgment"] = run.judgment.decision.model_dump(mode="json")
    record["judge_engine_divergences"] = [d.model_dump() for d in run.judgment.divergences]
    record["judge_jury_agreement"] = run.judge_jury_agreement
    return record


def _known_ids(run: "TrialRun", registry: LegalRuleRegistry) -> Set[str]:
    ids = {f.fact_id for f in run.case.facts}
    ids |= {e.evidence_id for e in run.case.evidence}
    ids |= {w.witness_id for w in run.case.witnesses}
    ids |= set(registry.rule_ids)
    ids |= {a.argument_id for a in run.arguments}
    ids |= {m.message_id for m in run.messages}
    return ids


def audit_trial(
    run: "TrialRun",
    provider: Optional[LLMProvider] = None,
    log: Optional[InteractionLog] = None,
    max_attempts: int = 3,
    registry: Optional[LegalRuleRegistry] = None,
) -> ProcessAudit:
    """Audit a finished trial: deterministic checks, plus the auditor agent if given"""
    registry = registry or LegalRuleRegistry()
    findings = deterministic_findings(run, registry)

    auditor_result = None
    if provider is not None:
        agent = AuditorAgent(provider, log=log, max_attempts=max_attempts)
        participants = {m.sender for m in run.messages}
        stages = {e["stage"] for e in run.event_history}
        auditor_result = agent.audit(
            run.case.case_id,
            build_dossier(run, registry),
            findings,
            participants,
            stages,
            _known_ids(run, registry),
        )

    all_findings = findings + (auditor_result.findings if auditor_result else [])
    metadata: Dict[str, Any] = {"deterministic_only": auditor_result is None}
    final_assessment = None
    if auditor_result is not None:
        output = auditor_result.output
        final_assessment = output.final_assessment
        metadata["decision_chain"] = [c.model_dump(mode="json") for c in output.decision_chain]
        metadata["auditor_model"] = auditor_result.model
    report = build_audit_report(run.case.case_id, all_findings, final_assessment, metadata)
    return ProcessAudit(findings=all_findings, report=report, auditor=auditor_result)
