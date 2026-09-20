"use client";

/**
 * Live simulation: every event the backend streams, as it arrives.
 *
 * This is the raw record of the trial - the same event history the run keeps -
 * so nothing here is inferred. The panels interpret; this only reports.
 */

import { useEffect, useRef, useState } from "react";

import {
  agentLabel,
  agentSeat,
  clockTime,
  describeEvent,
  seatStyle,
  stageLabel,
} from "@/lib/court";
import type { CourtEvent } from "@/lib/types";
import { Badge, Empty, cx } from "@/components/ui";

const EVENT_STYLES: Record<string, string> = {
  AGENT_ARGUMENT: "border-slate-700 bg-slate-900/60",
  AGENT_RESPONSE: "border-orange-500/30 bg-orange-500/5",
  EVIDENCE_ANALYZED: "border-emerald-500/30 bg-emerald-500/5",
  EVIDENCE_REVIEWED: "border-emerald-500/20 bg-emerald-500/5",
  JUDGE_QUESTION: "border-amber-500/30 bg-amber-500/5",
  JURY_DECISION: "border-violet-500/20 bg-violet-500/5",
  JURY_VERDICT: "border-violet-500/40 bg-violet-500/10",
  JUDGE_DECISION: "border-amber-500/50 bg-amber-500/10",
  AUDIT_COMPLETED: "border-slate-500/40 bg-slate-500/10",
  STAGE_SKIPPED: "border-slate-800 bg-slate-950/40",
  CASE_COMPLETE: "border-emerald-500/50 bg-emerald-500/10",
};

export function LiveFeed({
  events,
  live,
}: {
  events: CourtEvent[];
  live: boolean;
}) {
  const [showStarts, setShowStarts] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const shown = showStarts
    ? events
    : events.filter((event) => event.event_type !== "AGENT_STARTED");

  useEffect(() => {
    if (live) bottom.current?.scrollIntoView({ block: "nearest" });
  }, [shown.length, live]);

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs text-slate-500">
          {shown.length} events
          {live && <span className="ms-2 text-amber-300">· live</span>}
        </p>
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          <input
            type="checkbox"
            checked={showStarts}
            onChange={(e) => setShowStarts(e.target.checked)}
            className="size-3.5 rounded border-slate-600 bg-slate-900 accent-amber-500"
          />
          show agent starts
        </label>
      </div>

      {shown.length === 0 ? (
        <Empty>Waiting for the first event…</Empty>
      ) : (
        <ul className="scroll-panel max-h-[520px] space-y-1.5 overflow-y-auto pe-1">
          {shown.map((event, index) => {
            const seat = agentSeat(event.agent_id);
            return (
              <li
                key={`${event.timestamp}-${event.event_type}-${index}`}
                className={cx(
                  "rounded-lg border px-3 py-2",
                  EVENT_STYLES[event.event_type] ??
                    "border-slate-800 bg-slate-900/40",
                )}
              >
                <div className="flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="font-mono text-slate-500">
                    {clockTime(event.timestamp)}
                  </span>
                  <Badge className="border-slate-700 bg-slate-800/60 text-slate-400">
                    {stageLabel(event.stage)}
                  </Badge>
                  {event.agent_id && (
                    <span className={seatStyle(seat).text}>
                      {agentLabel(event.agent_id)}
                    </span>
                  )}
                  <span className="ms-auto font-mono text-[10px] text-slate-600">
                    {event.event_type}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-200">
                  {describeEvent(event)}
                </p>
              </li>
            );
          })}
          <div ref={bottom} />
        </ul>
      )}
    </div>
  );
}
