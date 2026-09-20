/**
 * The courtroom timeline: the spec's section 14 procedure top to bottom, with
 * each stage marked done, running, skipped, or still to come.
 */

import { seatStyle, stageLabel, stageSide } from "@/lib/court";
import type { StageState } from "@/lib/runState";
import { cx } from "@/components/ui";

const MARKS: Record<StageState, { symbol: string; className: string }> = {
  done: { symbol: "✓", className: "border-emerald-500/50 bg-emerald-500/15 text-emerald-300" },
  active: { symbol: "●", className: "border-amber-400/70 bg-amber-500/20 text-amber-200" },
  skipped: { symbol: "–", className: "border-slate-700 bg-slate-900 text-slate-600" },
  pending: { symbol: "", className: "border-slate-700 bg-slate-950 text-slate-600" },
};

export function Timeline({
  stages,
}: {
  stages: { stage: string; state: StageState }[];
}) {
  return (
    <ol className="relative space-y-1">
      <span
        aria-hidden
        className="absolute inset-y-2 left-[11px] w-px bg-slate-800"
      />
      {stages.map(({ stage, state }) => {
        const mark = MARKS[state];
        const side = seatStyle(stageSide(stage));
        return (
          <li key={stage} className="relative flex items-center gap-3">
            <span
              className={cx(
                "z-10 flex size-6 shrink-0 items-center justify-center rounded-full border text-[11px]",
                mark.className,
                state === "active" && "speaking",
              )}
            >
              {mark.symbol}
            </span>
            <span
              className={cx(
                "text-sm",
                state === "pending" && "text-slate-600",
                state === "skipped" && "text-slate-600 line-through",
                state === "done" && "text-slate-300",
                state === "active" && cx(side.text, "font-medium"),
              )}
            >
              {stageLabel(stage)}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
