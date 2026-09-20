/** One simulation in a list: what it was, how it ended, where it got to */

import Link from "next/link";

import {
  STATUS_STYLES,
  clockTime,
  duration,
  stageLabel,
  titleCase,
} from "@/lib/court";
import type { RunSummary } from "@/lib/types";
import { Badge } from "@/components/ui";

export function RunRow({ run }: { run: RunSummary }) {
  return (
    <li className="py-2.5">
      <Link
        href={`/runs/${run.run_id}`}
        className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md px-1 py-1 hover:bg-slate-800/40"
      >
        <Badge className={STATUS_STYLES[run.status]}>
          {titleCase(run.status)}
        </Badge>
        <span className="font-mono text-xs text-slate-400">
          {run.run_id.slice(0, 8)}
        </span>
        <span className="text-sm text-slate-200">{run.case_id}</span>
        <Badge>{run.mode}</Badge>
        <span className="text-xs text-slate-500">
          {run.current_stage ? stageLabel(run.current_stage) : "not started"}
          {" · "}
          {run.event_count} events
        </span>
        <span className="ms-auto text-xs text-slate-500">
          {clockTime(run.created_at)}
          {run.started_at &&
            ` · ${duration(run.started_at, run.finished_at)}`}
        </span>
      </Link>
      {run.error && (
        <p className="mt-1 ps-1 text-xs text-rose-300">{run.error}</p>
      )}
    </li>
  );
}
