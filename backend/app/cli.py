"""Command-line entry point

    python -m app.cli judge CASE_001                      # provider from settings / .env
    python -m app.cli judge CASE_001 --provider anthropic
    python -m app.cli judge CASE_001 --provider local --model llama3.1
    python -m app.cli judge CASE_001 --show-prompt        # print the prompt, call nothing
    python -m app.cli judge CASE_001 --json               # full run as JSON

    python -m app.cli court CASE_001                      # the full procedure (LangGraph)
    python -m app.cli court CASE_001 --events             # watch each stage as it happens
    python -m app.cli court CASE_001 --show-graph         # the state machine, as Mermaid
    python -m app.cli court CASE_001 --question-rounds 2 --no-cross-examination

    python -m app.cli trial CASE_001                      # a custom stage plan (linear)
    python -m app.cli trial CASE_001 --quick              # openings and closings only
    python -m app.cli trial CASE_001 --show-prompt        # prosecution opening prompt
    python -m app.cli trial CASE_001 --no-evidence        # without the Evidence Agent
    python -m app.cli trial CASE_001 --no-jury            # without the jury
    python -m app.cli trial CASE_001 --jurors 5 --jury-rule majority --no-deliberation
    python -m app.cli trial CASE_001 --no-audit           # without LEGAL_PROCESS_AUDIT
    python -m app.cli trial CASE_001 --json > run.json
    python -m app.cli audit run.json                      # re-audit a saved trial
    python -m app.cli audit run.json --deterministic-only # no model call

    python -m app.cli evidence CASE_001                   # evidence analysis only
    python -m app.cli evidence CASE_001 --show-prompt

    python -m app.cli serve                               # HTTP API + docs at /docs
    python -m app.cli serve --host 0.0.0.0 --port 8000    # reachable on your network

Research simulation only. This system does not provide legal advice or
determine real legal rights or obligations.
"""

import argparse
import os
import sys
from typing import Any, List, Optional

from app.agents import AdvocateAgent, AdvocateRole, AgentError, EvidenceAgent, JuryRule
from app.agents.judge import DISCLAIMER, JudgeAgent
from app.domain import CourtStage
from app.llm import (
    SUPPORTED_PROVIDERS,
    InteractionLog,
    LLMError,
    LLMProvider,
    ScriptedProvider,
    create_provider,
    provider_from_settings,
)
from app.rules import RuleEngine
from app.seed import get_bindings_for_case, get_case_by_id
from app.workflow import (
    DEFAULT_DEBATE_STAGES,
    TrialRun,
    audit_trial,
    QUICK_DEBATE_STAGES,
    WorkflowError,
    court_graph_mermaid,
    run_adversarial_trial,
    run_court,
    run_evidence_analysis,
    run_judge_only,
)


def _load_settings() -> Optional[Any]:
    """Application settings, or None if pydantic-settings is unavailable"""
    try:
        from app.config import settings
    except ImportError:
        return None
    return settings


def _build_provider(args: argparse.Namespace, settings: Optional[Any]) -> LLMProvider:
    if args.provider is None and settings is not None:
        if args.model:
            settings = settings.model_copy(update={f"{settings.llm_provider}_model": args.model})
        return provider_from_settings(settings)

    name = args.provider or os.environ.get("LLM_PROVIDER", "anthropic")
    return create_provider(name, model=args.model)


def _print_judgment(result: Any) -> None:
    decision = result.decision
    print("\nDECISION")
    for charge in decision.charge_decisions:
        print(f"  {charge.charge} [{charge.rule_id}]: {charge.decision.value.upper()} "
              f"(confidence {charge.confidence:.2f})")
        for element in charge.elements:
            cited = ", ".join(element.fact_ids + element.evidence_ids) or "none"
            print(f"    {element.condition_id} {element.assessment.value:<16} cites: {cited}")
        print(f"    {charge.reasoning}")

    if decision.arguments_considered:
        print(f"\nARGUMENTS WEIGHED: {', '.join(decision.arguments_considered)}")

    print("\nANALYSIS")
    print(f"  {decision.analysis}")

    if decision.unresolved_questions:
        print("\nUNRESOLVED")
        for question in decision.unresolved_questions:
            print(f"  - {question}")

    if result.divergences:
        print("\nDIVERGENCES FROM RULE ENGINE")
        for d in result.divergences:
            where = " ".join(x for x in (d.charge, d.rule_id, d.condition_id) if x)
            direction = "against defendant" if d.against_defendant else "for defendant"
            print(f"  - {d.kind} {where}: judge={d.judge_view}, "
                  f"engine={d.engine_view} ({direction})")


def _print_summary(run: Any) -> None:
    result = run.result
    print(f"\n{run.case.case_id} - {run.case.title}")
    print(f"Defendant: {run.case.defendant}")
    print(f"Model: {result.provider}/{result.model}  (prompt {result.prompt_version})")
    print(
        f"Attempts: {len(result.attempts)} ({result.rejected_attempts} rejected)  "
        f"Tokens: {result.usage.input_tokens} in / {result.usage.output_tokens} out"
    )
    _print_judgment(result)
    print(f"\n{DISCLAIMER}")


def _print_analysis(analysis: Any) -> None:
    output = analysis.output
    rejected = f", {analysis.rejected_attempts} rejected" if analysis.rejected_attempts else ""
    print(f"\n[EVIDENCE_ANALYSIS] evidence_agent ({analysis.model}{rejected})")
    print(f"  {output.summary}")
    print("\n  CLAIMS")
    for claim in output.claims:
        support = ", ".join(claim.supporting_evidence_ids + claim.supporting_witness_ids)
        contra = ", ".join(claim.contradicting_evidence_ids + claim.contradicting_witness_ids)
        print(f"    [{claim.status.value:<11}] {claim.claim}")
        print(f"        for: {support or '-'}   against: {contra or '-'}")
    if output.contradictions:
        print("\n  CONTRADICTIONS")
        for c in output.contradictions:
            items = ", ".join(c.evidence_ids + c.witness_ids + c.fact_ids)
            print(f"    - {c.description} ({items})")
    print("\n  WITNESSES")
    for w in output.witnesses:
        grounds = "; ".join(w.grounds) or "no challenge grounds"
        print(f"    {w.witness_id} {w.rating.value:<9} {grounds}")
    if output.missing_evidence:
        print("\n  MISSING EVIDENCE")
        for m in output.missing_evidence:
            elements = ", ".join(f"{e.rule_id}.{e.condition_id}" for e in m.elements)
            print(f"    - {m.description} [{elements}]")
    gaps = [p for p in analysis.provenance if p.gaps]
    if gaps:
        print("\n  PROVENANCE GAPS (from the record)")
        for p in gaps:
            print(f"    {p.evidence_id}: {'; '.join(p.gaps)}")
    for flag in analysis.flags:
        print(f"  flag ({flag.kind}): {flag.detail}")


def _print_review(review: Any) -> None:
    rejected = f", {review.rejected_attempts} rejected" if review.rejected_attempts else ""
    print(f"\n[EVIDENCE_REVIEW] evidence_agent ({review.model}{rejected})")
    print(f"  {review.output.summary}")
    for r in review.output.reviews:
        print(f"  {r.argument_id}: {r.support.value}")
        for issue in r.issues:
            print(f"      issue: {issue}")
    for flag in review.flags:
        print(f"  flag ({flag.kind}): {flag.detail}")


def _print_jury(run: Any) -> None:
    rounds = [("JURY_INDEPENDENT_DELIBERATION", run.jury_independent)]
    if run.jury_deliberation:
        rounds.append(("JURY_DELIBERATION", run.jury_deliberation))
    for stage, decisions in rounds:
        print(f"\n[{stage}]")
        for d in decisions:
            rejected = f", {d.rejected_attempts} rejected" if d.rejected_attempts else ""
            changed = f"  (changed: {', '.join(d.changed_charges)})" if d.changed_charges else ""
            print(f"  {d.juror_id} ({d.model}{rejected}): {d.verdict.decision}{changed}")
            for v in d.output.charge_verdicts:
                cited = ", ".join(v.fact_ids + v.evidence_ids + v.witness_ids) or "none"
                print(f"      {v.charge}: {v.verdict.value} ({v.confidence:.2f}) cites: {cited}")
            for uncertainty in d.output.uncertainties:
                print(f"      unsure: {uncertainty}")

    result = run.jury_result
    print(f"\n[JURY VERDICT] rule: {result.rule.value}")
    for tally in result.final:
        print(
            f"  {tally.charge}: {tally.outcome.value.upper()} "
            f"({len(tally.guilty)} guilty / {len(tally.not_guilty)} not guilty)"
        )
    line = f"  agreement: {result.independent_agreement:.2f} independent"
    if result.deliberated:
        line += (
            f" -> {result.final_agreement:.2f} after deliberation "
            f"({len(result.vote_changes)} vote change(s))"
        )
    print(line)


def _print_audit(audit: Any) -> None:
    report = audit.report
    meta = report.metadata
    source = "deterministic checks only" if meta["deterministic_only"] else (
        f"deterministic checks + auditor agent ({meta.get('auditor_model', '')})"
    )
    print(f"\n[LEGAL_PROCESS_AUDIT] {report.audit_id} - {source}")
    counts = ", ".join(f"{n} {s}" for s, n in meta["severity_counts"].items() if n)
    print(f"  overall: {meta['overall_status'].upper()} ({counts or 'no findings'})")
    for finding in audit.findings:
        where = " ".join(x for x in (finding.agent_id, finding.stage) if x)
        print(
            f"  {finding.finding_id} [{finding.severity.value:<8}] {finding.category.value:<13} "
            f"{finding.check}{f' ({where})' if where else ''}"
        )
        print(f"      {finding.description}")
    for link in meta.get("decision_chain", []):
        print(f"  chain {link['link']}: {link['rating']} - {link['note']}")
    print(f"  assessment: {report.final_assessment}")


def _print_questions(question_round: Any) -> None:
    rejected = (
        f", {question_round.rejected_attempts} rejected" if question_round.rejected_attempts else ""
    )
    print(
        f"\n[JUDGE_QUESTIONS] judge_agent, round {question_round.round} "
        f"({question_round.model}{rejected})"
    )
    print(f"  flagged as unsupported: {', '.join(question_round.flagged_argument_ids)}")
    for question in question_round.questions:
        about = ", ".join(question.argument_ids)
        print(f"  {question.question_id} -> {question.addressed_to} (about {about})")
        print(f"      {question.question}")


def _print_event(entry: dict) -> None:
    """One line per event, for --events"""
    details = {
        k: v
        for k, v in entry.items()
        if k not in ("stage", "event_type", "timestamp") and v not in ([], {}, None, "")
    }
    summary = ", ".join(f"{k}={v}" for k, v in list(details.items())[:4])
    print(f"  {entry['stage']:<30} {entry['event_type']:<18} {summary}"[:160], flush=True)


def _print_trial(run: Any) -> None:
    print(f"\n{run.case.case_id} - {run.case.title}")
    print(f"Defendant: {run.case.defendant}")
    usage = run.usage
    print(f"Tokens: {usage.input_tokens} in / {usage.output_tokens} out")

    if run.evidence_analysis is not None:
        _print_analysis(run.evidence_analysis)

    # Walk the event history so each stage prints where it happened.
    reviews = iter(run.evidence_reviews)
    question_rounds = iter(run.judge_question_rounds)
    turn_index = 0
    for entry in run.event_history:
        if entry["event_type"] == "EVIDENCE_REVIEWED":
            _print_review(next(reviews))
            continue
        if entry["event_type"] == "JUDGE_QUESTION":
            _print_questions(next(question_rounds))
            continue
        if entry["event_type"] not in ("AGENT_ARGUMENT", "AGENT_RESPONSE"):
            continue
        turn = run.turns[turn_index]
        turn_index += 1
        rejected = f", {turn.rejected_attempts} rejected" if turn.rejected_attempts else ""
        print(f"\n[{turn.stage.value}] {turn.agent_id} ({turn.model}{rejected})")
        print(f"  {turn.statement}")
        for argument in turn.arguments:
            answers = (
                f"  (answers {', '.join(argument.counter_argument_ids)})"
                if argument.counter_argument_ids
                else ""
            )
            print(f"  {argument.argument_id}: {argument.claim}{answers}")
            cited = argument.fact_ids + argument.evidence_ids + argument.witness_ids
            print(f"      cites: {', '.join(cited)}")
            for assumption in argument.metadata.get("assumptions", []):
                print(f"      assumes: {assumption}")
        for flag in turn.flags:
            print(f"  flag (argument {flag.argument_index}): {flag.detail}")

    if run.jury_result is not None:
        _print_jury(run)

    judgment = run.judgment
    rejected = f", {judgment.rejected_attempts} rejected" if judgment.rejected_attempts else ""
    print(f"\n[JUDGE_DECISION] judge_agent ({judgment.model}{rejected})")
    _print_judgment(judgment)
    for row in run.judge_jury_agreement:
        verdict = "agrees with" if row["agrees"] else "differs from"
        print(f"  {row['charge']}: judge {verdict} jury ({row['judge']} vs {row['jury']})")
    if run.audit is not None:
        _print_audit(run.audit)
    print(f"\n{DISCLAIMER}")


def _judge(args: argparse.Namespace) -> int:
    settings = _load_settings()

    if args.show_prompt:
        case = get_case_by_id(args.case_id)
        if case is None:
            print(f"Unknown case '{args.case_id}'", file=sys.stderr)
            return 2
        evaluation = RuleEngine().evaluate_case(case, get_bindings_for_case(case.case_id))

        # An empty scripted provider: building the request never calls a model.
        request = JudgeAgent(ScriptedProvider([])).build_request(case, evaluation)
        print("=== SYSTEM ===\n" + request.system)
        print("\n=== USER ===\n" + request.messages[0].content)
        return 0

    try:
        provider = _build_provider(args, settings)
    except LLMError as exc:
        print(f"Provider error: {exc}", file=sys.stderr)
        return 2

    log_path = args.log_file
    if log_path is None and settings is not None:
        log_path = settings.llm_log_path
    log = InteractionLog(log_path)
    max_attempts = args.max_attempts or (settings.llm_max_attempts if settings else 3)

    try:
        run = run_judge_only(
            args.case_id,
            provider,
            log=log,
            max_attempts=max_attempts,
            strict_engine_alignment=args.strict,
        )
    except (WorkflowError, AgentError) as exc:
        print(f"Simulation failed: {exc}", file=sys.stderr)
        for attempt in getattr(exc, "attempts", []):
            print(f"  attempt {attempt.attempt}: {'; '.join(attempt.errors)}", file=sys.stderr)
        return 1

    if args.json:
        print(run.model_dump_json(indent=2))
    else:
        _print_summary(run)
        if log_path:
            print(f"Interactions logged to {log_path}")
    return 0


def _trial(args: argparse.Namespace) -> int:
    settings = _load_settings()
    stages = QUICK_DEBATE_STAGES if args.quick else DEFAULT_DEBATE_STAGES
    if args.no_evidence:
        stages = [s for s in stages if s != CourtStage.EVIDENCE_REVIEW]

    if args.show_prompt:
        case = get_case_by_id(args.case_id)
        if case is None:
            print(f"Unknown case '{args.case_id}'", file=sys.stderr)
            return 2
        evaluation = RuleEngine().evaluate_case(case, get_bindings_for_case(case.case_id))
        advocate = AdvocateAgent(AdvocateRole.PROSECUTION, ScriptedProvider([]))
        request = advocate.build_request(case, evaluation, CourtStage.PROSECUTION_OPENING)
        print("=== SYSTEM ===\n" + request.system)
        print("\n=== USER ===\n" + request.messages[0].content)
        return 0

    try:
        provider = _build_provider(args, settings)
    except LLMError as exc:
        print(f"Provider error: {exc}", file=sys.stderr)
        return 2

    log_path = args.log_file
    if log_path is None and settings is not None:
        log_path = settings.llm_log_path
    log = InteractionLog(log_path)
    max_attempts = args.max_attempts or (settings.llm_max_attempts if settings else 3)

    try:
        run = run_adversarial_trial(
            args.case_id,
            provider,
            log=log,
            stages=stages,
            evidence=not args.no_evidence,
            jury=not args.no_jury,
            jurors=args.jurors,
            deliberation=not args.no_deliberation,
            jury_rule=JuryRule(args.jury_rule),
            audit=not args.no_audit,
            audit_agent=not args.deterministic_audit,
            max_attempts=max_attempts,
            strict_engine_alignment=args.strict,
        )
    except (WorkflowError, AgentError) as exc:
        print(f"Simulation failed: {exc}", file=sys.stderr)
        for attempt in getattr(exc, "attempts", []):
            print(f"  attempt {attempt.attempt}: {'; '.join(attempt.errors)}", file=sys.stderr)
        return 1

    if args.json:
        print(run.model_dump_json(indent=2))
    else:
        _print_trial(run)
        if log_path:
            print(f"Interactions logged to {log_path}")
    return 0


def _court(args: argparse.Namespace) -> int:
    if args.show_graph:
        print(court_graph_mermaid())
        return 0

    settings = _load_settings()
    if args.show_prompt:
        case = get_case_by_id(args.case_id)
        if case is None:
            print(f"Unknown case '{args.case_id}'", file=sys.stderr)
            return 2
        evaluation = RuleEngine().evaluate_case(case, get_bindings_for_case(case.case_id))
        advocate = AdvocateAgent(AdvocateRole.PROSECUTION, ScriptedProvider([]))
        request = advocate.build_request(case, evaluation, CourtStage.PROSECUTION_OPENING)
        print("=== SYSTEM ===\n" + request.system)
        print("\n=== USER ===\n" + request.messages[0].content)
        return 0

    try:
        provider = _build_provider(args, settings)
    except LLMError as exc:
        print(f"Provider error: {exc}", file=sys.stderr)
        return 2

    log_path = args.log_file
    if log_path is None and settings is not None:
        log_path = settings.llm_log_path
    log = InteractionLog(log_path)
    max_attempts = args.max_attempts or (settings.llm_max_attempts if settings else 3)
    if args.events:
        print(f"{args.case_id}: the court is in session")

    try:
        run = run_court(
            args.case_id,
            provider,
            evidence=not args.no_evidence,
            cross_examination=not args.no_cross_examination,
            judge_questions=not args.no_judge_questions,
            max_question_rounds=args.question_rounds,
            jury=not args.no_jury,
            jurors=args.jurors,
            deliberation=not args.no_deliberation,
            jury_rule=JuryRule(args.jury_rule),
            audit=not args.no_audit,
            audit_agent=not args.deterministic_audit,
            log=log,
            max_attempts=max_attempts,
            strict_engine_alignment=args.strict,
            on_event=_print_event if args.events else None,
        )
    except (WorkflowError, AgentError) as exc:
        print(f"Simulation failed: {exc}", file=sys.stderr)
        for attempt in getattr(exc, "attempts", []):
            print(f"  attempt {attempt.attempt}: {'; '.join(attempt.errors)}", file=sys.stderr)
        return 1

    if args.json:
        print(run.model_dump_json(indent=2))
    else:
        _print_trial(run)
        if log_path:
            print(f"Interactions logged to {log_path}")
    return 0


def _evidence(args: argparse.Namespace) -> int:
    settings = _load_settings()

    if args.show_prompt:
        case = get_case_by_id(args.case_id)
        if case is None:
            print(f"Unknown case '{args.case_id}'", file=sys.stderr)
            return 2
        evaluation = RuleEngine().evaluate_case(case, get_bindings_for_case(case.case_id))
        request = EvidenceAgent(ScriptedProvider([])).build_analysis_request(case, evaluation)
        print("=== SYSTEM ===\n" + request.system)
        print("\n=== USER ===\n" + request.messages[0].content)
        return 0

    try:
        provider = _build_provider(args, settings)
    except LLMError as exc:
        print(f"Provider error: {exc}", file=sys.stderr)
        return 2

    log_path = args.log_file
    if log_path is None and settings is not None:
        log_path = settings.llm_log_path
    log = InteractionLog(log_path)
    max_attempts = args.max_attempts or (settings.llm_max_attempts if settings else 3)

    try:
        run = run_evidence_analysis(args.case_id, provider, log=log, max_attempts=max_attempts)
    except (WorkflowError, AgentError) as exc:
        print(f"Simulation failed: {exc}", file=sys.stderr)
        for attempt in getattr(exc, "attempts", []):
            print(f"  attempt {attempt.attempt}: {'; '.join(attempt.errors)}", file=sys.stderr)
        return 1

    if args.json:
        print(run.model_dump_json(indent=2))
    else:
        print(f"\n{run.case.case_id} - {run.case.title}")
        _print_analysis(run.analysis)
        print(f"\n{DISCLAIMER}")
        if log_path:
            print(f"Interactions logged to {log_path}")
    return 0


def _audit(args: argparse.Namespace) -> int:
    try:
        with open(args.run_file, encoding="utf-8") as handle:
            run = TrialRun.model_validate_json(handle.read())
    except (OSError, ValueError) as exc:
        print(f"Cannot load trial run '{args.run_file}': {exc}", file=sys.stderr)
        return 2

    settings = _load_settings()
    provider = None
    if not args.deterministic_only:
        try:
            provider = _build_provider(args, settings)
        except LLMError as exc:
            print(f"Provider error: {exc}", file=sys.stderr)
            return 2

    log_path = args.log_file
    if log_path is None and settings is not None:
        log_path = settings.llm_log_path
    log = InteractionLog(log_path) if provider is not None else None
    max_attempts = args.max_attempts or (settings.llm_max_attempts if settings else 3)

    try:
        audit = audit_trial(run, provider, log=log, max_attempts=max_attempts)
    except AgentError as exc:
        print(f"Audit failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(audit.model_dump_json(indent=2))
    else:
        print(f"\n{run.case.case_id} - {run.case.title} (saved run: {args.run_file})")
        _print_audit(audit)
        print(f"\n{DISCLAIMER}")
    return 0


def _serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "The 'uvicorn' package is not installed. Run: pip install \"uvicorn[standard]\"",
            file=sys.stderr,
        )
        return 2

    settings = _load_settings()
    port = args.port or (settings.api_port if settings else 8000)
    provider = getattr(settings, "llm_provider", "not configured") if settings else "not configured"
    print(f"Court Simulation API on http://{args.host}:{port}")
    print(f"  docs:     http://{args.host}:{port}/docs")
    print(f"  provider: {provider}")
    print(f"\n{DISCLAIMER}\n")
    uvicorn.run("app.api:app", host=args.host, port=port, reload=args.reload)
    return 0


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("case_id", help="Seeded case ID, e.g. CASE_001")
    parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS, help="Override LLM_PROVIDER")
    parser.add_argument("--model", help="Override the provider's model")
    parser.add_argument("--max-attempts", type=int, help="Generation attempts before giving up")
    parser.add_argument("--log-file", help="JSON Lines file for interaction logs")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Reject convictions the rule engine does not support",
    )
    parser.add_argument("--show-prompt", action="store_true", help="Print the prompt and exit")
    parser.add_argument("--json", action="store_true", help="Print the full run as JSON")


def _add_trial_options(parser: argparse.ArgumentParser) -> None:
    """Options shared by `court` and `trial`"""
    parser.add_argument(
        "--no-evidence",
        action="store_true",
        help="Skip the Evidence Agent (no EVIDENCE_ANALYSIS or EVIDENCE_REVIEW)",
    )
    parser.add_argument("--no-jury", action="store_true", help="Skip the jury")
    parser.add_argument("--jurors", type=int, default=3, help="Number of jurors (default 3)")
    parser.add_argument(
        "--no-deliberation",
        action="store_true",
        help="Independent jury verdicts only; no deliberation round",
    )
    parser.add_argument(
        "--jury-rule",
        choices=[r.value for r in JuryRule],
        default=JuryRule.UNANIMOUS.value,
        help="How votes become a verdict (default unanimous; a split is a hung jury)",
    )
    parser.add_argument("--no-audit", action="store_true", help="Skip LEGAL_PROCESS_AUDIT")
    parser.add_argument(
        "--deterministic-audit",
        action="store_true",
        help="Audit with deterministic checks only (no auditor agent call)",
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=DISCLAIMER)
    commands = parser.add_subparsers(dest="command", required=True)

    judge = commands.add_parser("judge", help="Run Case -> Judge Agent -> Decision")
    _add_run_options(judge)
    judge.set_defaults(handler=_judge)

    court = commands.add_parser(
        "court", help="Run the full court procedure (LangGraph state machine)"
    )
    _add_run_options(court)
    _add_trial_options(court)
    court.add_argument(
        "--no-cross-examination", action="store_true", help="Skip CROSS_EXAMINATION"
    )
    court.add_argument(
        "--no-judge-questions",
        action="store_true",
        help="The judge does not question parties about unsupported arguments",
    )
    court.add_argument(
        "--question-rounds",
        type=int,
        default=1,
        help="Most rounds of judge questions (default 1)",
    )
    court.add_argument(
        "--events", action="store_true", help="Print each event live as the court runs"
    )
    court.add_argument(
        "--show-graph", action="store_true", help="Print the state machine as Mermaid and exit"
    )
    court.set_defaults(handler=_court)

    trial = commands.add_parser("trial", help="Run a custom stage plan (linear runner)")
    _add_run_options(trial)
    _add_trial_options(trial)
    trial.add_argument(
        "--quick", action="store_true", help="Openings and closings only (4 advocate calls)"
    )
    trial.set_defaults(handler=_trial)

    audit = commands.add_parser("audit", help="Audit a saved trial run (from trial --json)")
    audit.add_argument("run_file", help="JSON file written by `trial --json`")
    audit.add_argument("--provider", choices=SUPPORTED_PROVIDERS, help="Override LLM_PROVIDER")
    audit.add_argument("--model", help="Override the provider's model")
    audit.add_argument("--max-attempts", type=int, help="Generation attempts before giving up")
    audit.add_argument("--log-file", help="JSON Lines file for interaction logs")
    audit.add_argument(
        "--deterministic-only", action="store_true", help="Run the deterministic checks only"
    )
    audit.add_argument("--json", action="store_true", help="Print the audit as JSON")
    audit.set_defaults(handler=_audit)

    serve = commands.add_parser("serve", help="Run the HTTP API (FastAPI + uvicorn)")
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind (default 127.0.0.1; use 0.0.0.0 to allow other machines)",
    )
    serve.add_argument("--port", type=int, help="Port (default from settings, else 8000)")
    serve.add_argument("--reload", action="store_true", help="Reload on code changes")
    serve.set_defaults(handler=_serve)

    evidence = commands.add_parser("evidence", help="Run the Evidence Agent's analysis only")
    _add_run_options(evidence)
    evidence.set_defaults(handler=_evidence)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
