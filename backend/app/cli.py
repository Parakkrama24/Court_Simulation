"""Command-line entry point

    python -m app.cli judge CASE_001                      # provider from settings / .env
    python -m app.cli judge CASE_001 --provider anthropic
    python -m app.cli judge CASE_001 --provider local --model llama3.1
    python -m app.cli judge CASE_001 --show-prompt        # print the prompt, call nothing
    python -m app.cli judge CASE_001 --json               # full run as JSON

    python -m app.cli trial CASE_001                      # Prosecution <-> Defense -> Judge
    python -m app.cli trial CASE_001 --quick              # openings and closings only
    python -m app.cli trial CASE_001 --show-prompt        # prosecution opening prompt

Research simulation only. This system does not provide legal advice or
determine real legal rights or obligations.
"""

import argparse
import os
import sys
from typing import Any, List, Optional

from app.agents import AdvocateAgent, AdvocateRole, AgentError
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
    QUICK_DEBATE_STAGES,
    WorkflowError,
    run_adversarial_trial,
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


def _print_trial(run: Any) -> None:
    print(f"\n{run.case.case_id} - {run.case.title}")
    print(f"Defendant: {run.case.defendant}")
    usage = run.usage
    print(f"Tokens: {usage.input_tokens} in / {usage.output_tokens} out")

    for turn in run.turns:
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

    judgment = run.judgment
    rejected = f", {judgment.rejected_attempts} rejected" if judgment.rejected_attempts else ""
    print(f"\n[JUDGE_DECISION] judge_agent ({judgment.model}{rejected})")
    _print_judgment(judgment)
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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=DISCLAIMER)
    commands = parser.add_subparsers(dest="command", required=True)

    judge = commands.add_parser("judge", help="Run Case -> Judge Agent -> Decision")
    _add_run_options(judge)
    judge.set_defaults(handler=_judge)

    trial = commands.add_parser("trial", help="Run Prosecution <-> Defense -> Judge")
    _add_run_options(trial)
    trial.add_argument(
        "--quick", action="store_true", help="Openings and closings only (4 advocate calls)"
    )
    trial.set_defaults(handler=_trial)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
