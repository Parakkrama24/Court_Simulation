"use client";

/** Every simulation this server remembers */

import { Loading, Problem } from "@/components/Problem";
import { RunRow } from "@/components/RunRow";
import { Card } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { listRuns } from "@/lib/api";

export default function RunsPage() {
  const runs = useApi(listRuns, [], { refreshMs: 5000 });

  if (runs.error) return <Problem error={runs.error} retry={runs.reload} />;
  if (!runs.data) return <Loading what="simulations" />;

  return (
    <Card
      title="Simulations"
      subtitle="Newest first. Runs live in the server's memory, so restarting it forgets them."
    >
      {runs.data.length === 0 ? (
        <p className="text-sm text-slate-500">
          Nothing has been run yet. Open a case and start a simulation.
        </p>
      ) : (
        <ul className="divide-y divide-slate-800">
          {runs.data.map((run) => (
            <RunRow key={run.run_id} run={run} />
          ))}
        </ul>
      )}
    </Card>
  );
}
