"use client";

/** Case selection: the seeded cases, and the simulations run so far */

import Link from "next/link";

import { Loading, Problem } from "@/components/Problem";
import { RunRow } from "@/components/RunRow";
import { Badge, Card, cx } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { listCases, listRuns } from "@/lib/api";
import { titleCase } from "@/lib/court";
import type { CaseSummary } from "@/lib/types";

export default function HomePage() {
  const cases = useApi(listCases, []);
  const runs = useApi(listRuns, [], { refreshMs: 5000 });

  return (
    <div className="space-y-8">
      <section>
        <h1 className="font-[family-name:var(--font-display)] text-2xl text-slate-100">
          Select a case
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          Each case is heard by a panel of language-model agents - prosecution,
          defense, an evidence analyst, a jury, and a judge - under the
          fictional laws of Arandia. A deterministic rule engine, not an agent,
          decides which legal elements the record actually supports.
        </p>
      </section>

      {cases.error && <Problem error={cases.error} retry={cases.reload} />}
      {cases.loading && !cases.data && <Loading what="cases" />}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(cases.data ?? []).map((item) => (
          <CaseCard key={item.case_id} summary={item} />
        ))}
      </div>

      <Card
        title="Simulations"
        subtitle="Runs this server remembers, newest first"
        right={
          <Link
            href="/runs"
            className="text-xs text-amber-300 hover:text-amber-200"
          >
            All runs →
          </Link>
        }
      >
        {runs.error ? (
          <p className="text-sm text-slate-500">{runs.error}</p>
        ) : (runs.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">
            No simulations yet. Open a case and start one.
          </p>
        ) : (
          <ul className="divide-y divide-slate-800">
            {(runs.data ?? []).slice(0, 5).map((run) => (
              <RunRow key={run.run_id} run={run} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function CaseCard({ summary }: { summary: CaseSummary }) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-slate-500">{summary.case_id}</p>
          <h2 className="mt-0.5 font-[family-name:var(--font-display)] text-lg text-slate-100">
            {summary.title}
          </h2>
        </div>
        {summary.runnable ? (
          <Badge className="border-emerald-500/40 bg-emerald-500/10 text-emerald-300">
            Ready to run
          </Badge>
        ) : (
          <Badge
            className="border-slate-600/60 bg-slate-800/60 text-slate-400"
            title="This case has no element bindings yet, so the rule engine cannot evaluate it"
          >
            Record only
          </Badge>
        )}
      </div>

      <p className="mt-3 text-sm text-slate-400">
        <span className="text-slate-500">Defendant</span> {summary.defendant}
      </p>

      <div className="mt-2 flex flex-wrap gap-1">
        {summary.charges.map((charge) => (
          <Badge
            key={charge}
            className="border-rose-500/30 bg-rose-500/10 text-rose-300"
          >
            {titleCase(charge)}
          </Badge>
        ))}
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-slate-800 pt-3 text-center">
        {[
          ["Facts", summary.facts],
          ["Evidence", summary.evidence],
          ["Witnesses", summary.witnesses],
        ].map(([label, value]) => (
          <div key={label}>
            <dd className="text-lg text-slate-200">{value}</dd>
            <dt className="text-[11px] tracking-wide text-slate-500 uppercase">
              {label}
            </dt>
          </div>
        ))}
      </dl>
    </>
  );

  return (
    <Link
      href={`/cases/${summary.case_id}`}
      className={cx(
        "block rounded-xl border p-4 transition-colors",
        summary.runnable
          ? "border-slate-700/60 bg-slate-900/40 hover:border-amber-500/40 hover:bg-slate-900/70"
          : "border-slate-800 bg-slate-900/20 hover:border-slate-600",
      )}
    >
      {body}
    </Link>
  );
}
