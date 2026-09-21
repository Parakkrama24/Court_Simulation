"use client";

/**
 * Start a simulation.
 *
 * Every option here is a field of the backend's `SimulationRequest`, and each
 * has a default there too, so an untouched form is a valid request. The
 * estimate is the number of model calls the chosen stages will make - a full
 * court run is minutes of work, so it is worth seeing before starting.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { startSimulation } from "@/lib/api";
import type { RunMode, SimulationRequest } from "@/lib/types";
import { Badge, cx } from "@/components/ui";

const DEFAULTS: SimulationRequest = {
  mode: "court",
  provider: null,
  model: null,
  evidence: true,
  cross_examination: true,
  judge_questions: true,
  question_rounds: 1,
  jury: true,
  jurors: 3,
  deliberation: true,
  jury_rule: "unanimous",
  audit: true,
  audit_agent: true,
  max_attempts: 3,
  strict_engine_alignment: false,
};

/** The backend's SUPPORTED_PROVIDERS; "" leaves the choice to the server */
const PROVIDERS = [
  { value: "", label: "Server default (LLM_PROVIDER in .env)" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "local", label: "Local (OpenAI-compatible server)" },
];

const MODES: { id: RunMode; label: string; description: string }[] = [
  {
    id: "court",
    label: "Full court",
    description: "The whole spec section 14 procedure, from openings to audit",
  },
  {
    id: "judge",
    label: "Judge only",
    description: "The case straight to the judge - one call",
  },
  {
    id: "evidence",
    label: "Evidence only",
    description: "The Evidence Agent's analysis - one call",
  },
];

/**
 * At most how many model calls the chosen options will make.
 *
 * An upper bound: the judge only asks questions when the evidence review
 * flagged something, so a clean trial makes fewer calls than this.
 */
export function estimateCalls(options: SimulationRequest): number {
  if (options.mode !== "court") return 1;
  let calls = 8; // openings, arguments, rebuttals, closings - two each
  if (options.evidence) calls += 2; // the analysis, and the review of the arguments
  if (options.cross_examination) calls += 2; // each party cross-examines
  if (options.judge_questions && options.evidence) {
    // per round: the questions, the answer, and the review of that answer
    calls += options.question_rounds * 3;
  }
  if (options.jury) {
    calls += options.jurors;
    if (options.deliberation && options.jurors > 1) calls += options.jurors;
  }
  calls += 1; // the judgment
  if (options.audit && options.audit_agent) calls += 1;
  return calls;
}

export function SimulationForm({
  caseId,
  runnable,
}: {
  caseId: string;
  runnable: boolean;
}) {
  const router = useRouter();
  const [options, setOptions] = useState<SimulationRequest>(DEFAULTS);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof SimulationRequest>(
    key: K,
    value: SimulationRequest[K],
  ) => setOptions((current) => ({ ...current, [key]: value }));

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const run = await startSimulation(caseId, {
        ...options,
        provider: options.provider || null,
        model: options.model || null,
      });
      router.push(`/runs/${run.run_id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setStarting(false);
    }
  };

  const court = options.mode === "court";

  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-3">
        {MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            onClick={() => set("mode", mode.id)}
            className={cx(
              "rounded-lg border p-3 text-left transition-colors",
              options.mode === mode.id
                ? "border-amber-500/50 bg-amber-500/10"
                : "border-slate-700/60 bg-slate-900/40 hover:border-slate-600",
            )}
          >
            <span className="block text-sm text-slate-100">{mode.label}</span>
            <span className="mt-0.5 block text-xs text-slate-400">
              {mode.description}
            </span>
          </button>
        ))}
      </div>

      {court && (
        <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <Toggle
            label="Evidence Agent"
            hint="Neutral analysis before the debate, and review of the arguments"
            checked={options.evidence}
            onChange={(value) => set("evidence", value)}
          />
          <Toggle
            label="Cross-examination"
            hint="Each party questions the other's witnesses"
            checked={options.cross_examination}
            onChange={(value) => set("cross_examination", value)}
          />
          <Toggle
            label="Judge questions"
            hint="The judge presses a party on arguments the review found unsupported"
            checked={options.judge_questions}
            onChange={(value) => set("judge_questions", value)}
          />
          <Number
            label="Question rounds"
            min={0}
            max={5}
            value={options.question_rounds}
            onChange={(value) => set("question_rounds", value)}
            disabled={!options.judge_questions}
          />
          <Toggle
            label="Jury"
            hint="Jurors decide independently, then deliberate once"
            checked={options.jury}
            onChange={(value) => set("jury", value)}
          />
          <Number
            label="Jurors"
            min={1}
            max={12}
            value={options.jurors}
            onChange={(value) => set("jurors", value)}
            disabled={!options.jury}
          />
          <Toggle
            label="Deliberation round"
            hint="Each juror reconsiders once, seeing the whole panel"
            checked={options.deliberation}
            onChange={(value) => set("deliberation", value)}
            disabled={!options.jury || options.jurors < 2}
          />
          <label className="flex items-center justify-between gap-3 text-sm">
            <span className="text-slate-300">Jury rule</span>
            <select
              value={options.jury_rule}
              disabled={!options.jury}
              onChange={(e) =>
                set("jury_rule", e.target.value as "unanimous" | "majority")
              }
              className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200 disabled:opacity-40"
            >
              <option value="unanimous">Unanimous</option>
              <option value="majority">Majority</option>
            </select>
          </label>
          <Toggle
            label="Process audit"
            hint="Deterministic checks over the whole trial"
            checked={options.audit}
            onChange={(value) => set("audit", value)}
          />
          <Toggle
            label="Auditor agent"
            hint="An LLM auditor on top of the deterministic checks"
            checked={options.audit_agent}
            onChange={(value) => set("audit_agent", value)}
            disabled={!options.audit}
          />
        </div>
      )}

      <details className="rounded-lg border border-slate-800 bg-slate-900/30 p-3">
        <summary className="cursor-pointer text-sm text-slate-300">
          Provider and model
        </summary>
        <p className="mt-2 text-xs text-slate-500">
          API keys never go here. The server reads them from{" "}
          <code className="text-slate-400">.env</code> (
          <code className="text-slate-400">OPENAI_API_KEY</code> or{" "}
          <code className="text-slate-400">ANTHROPIC_API_KEY</code>) - restart
          the backend after adding one.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="block text-xs text-slate-500">Provider</span>
            {/* A fixed list, not a text box: a pasted API key has nowhere to go. */}
            <select
              value={options.provider ?? ""}
              onChange={(e) => set("provider", e.target.value || null)}
              className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-200"
            >
              {PROVIDERS.map((provider) => (
                <option key={provider.value} value={provider.value}>
                  {provider.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="block text-xs text-slate-500">Model</span>
            <input
              value={options.model ?? ""}
              onChange={(e) => set("model", e.target.value)}
              placeholder="claude-opus-5, gpt-4o, llama3.1"
              className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-200"
            />
          </label>
          <Number
            label="Attempts per agent"
            min={1}
            max={5}
            value={options.max_attempts}
            onChange={(value) => set("max_attempts", value)}
          />
          <Toggle
            label="Strict engine alignment"
            hint="Reject a judgment that contradicts the rule engine"
            checked={options.strict_engine_alignment}
            onChange={(value) => set("strict_engine_alignment", value)}
          />
        </div>
      </details>

      {error && (
        <p className="rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-sm text-rose-200">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={start}
          disabled={starting || !runnable}
          className="rounded-md bg-amber-500/90 px-4 py-2 text-sm font-medium text-slate-950 transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
        >
          {starting ? "Starting…" : "Start simulation"}
        </button>
        <Badge title="Each call is one request to the configured model">
          ≈ {estimateCalls(options)} model calls
        </Badge>
        {!runnable && (
          <span className="text-xs text-amber-300">
            This case has no element bindings, so the backend will not run it.
          </span>
        )}
      </div>
    </div>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label
      className={cx(
        "flex items-start gap-2.5 text-sm",
        disabled && "opacity-40",
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 size-4 rounded border-slate-600 bg-slate-900 accent-amber-500"
      />
      <span>
        <span className="block text-slate-200">{label}</span>
        {hint && <span className="block text-xs text-slate-500">{hint}</span>}
      </span>
    </label>
  );
}

function Number({
  label,
  value,
  min,
  max,
  onChange,
  disabled,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
  disabled?: boolean;
}) {
  return (
    <label
      className={cx(
        "flex items-center justify-between gap-3 text-sm",
        disabled && "opacity-40",
      )}
    >
      <span className="text-slate-300">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(e) => {
          const next = parseInt(e.target.value, 10);
          if (!isNaN(next)) onChange(Math.min(max, Math.max(min, next)));
        }}
        className="w-20 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-200"
      />
    </label>
  );
}
