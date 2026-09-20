/**
 * Jury panel: how each juror decided on their own, and again after seeing the
 * panel.
 *
 * The tally is computed by the backend's verdict engine, not by a juror - the
 * jurors only vote. A juror who changed their mind is marked, because that is
 * the one thing deliberation is for.
 */

import { agentLabel, percent, titleCase, verdictLabel } from "@/lib/court";
import type { ChargeTally, JurorDecision, JuryResult } from "@/lib/types";
import { Badge, Empty, IdList, Meter, cx } from "@/components/ui";

const OUTCOME_STYLES: Record<string, string> = {
  guilty: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  not_guilty: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  hung: "border-amber-500/40 bg-amber-500/10 text-amber-300",
};

export function JuryPanel({
  independent,
  deliberation,
  result,
}: {
  independent: JurorDecision[];
  deliberation: JurorDecision[];
  result: JuryResult | null;
}) {
  if (independent.length === 0 && !result) {
    return <Empty>No jury sat in this simulation.</Empty>;
  }

  return (
    <div className="space-y-5">
      {result && (
        <section>
          <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
            The verdict, charge by charge
          </h3>
          <p className="mb-2 text-xs text-slate-500">
            Decision rule: {titleCase(result.rule)} · {result.jurors.length}{" "}
            jurors
            {result.deliberated ? " · deliberated once" : " · no deliberation"}
          </p>
          <ul className="space-y-2">
            {result.final.map((tally) => (
              <TallyCard
                key={tally.charge}
                tally={tally}
                before={result.independent.find(
                  (row) => row.charge === tally.charge,
                )}
              />
            ))}
          </ul>
        </section>
      )}

      {result && result.vote_changes.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
            Changed after deliberation
          </h3>
          <ul className="space-y-1">
            {result.vote_changes.map((change, index) => (
              <li
                key={index}
                className="rounded-lg border border-violet-500/30 bg-violet-500/5 px-3 py-2 text-sm text-slate-200"
              >
                {agentLabel(change.juror_id)} changed on{" "}
                {titleCase(change.charge)}: {verdictLabel(change.from)} →{" "}
                {verdictLabel(change.to)}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
          Each juror
        </h3>
        <div className="grid gap-3 lg:grid-cols-2">
          {independent.map((decision) => (
            <JurorCard
              key={decision.juror_id}
              independent={decision}
              after={deliberation.find(
                (other) => other.juror_id === decision.juror_id,
              )}
            />
          ))}
        </div>
      </section>
    </div>
  );
}

function TallyCard({
  tally,
  before,
}: {
  tally: ChargeTally;
  before?: ChargeTally;
}) {
  const total = tally.guilty.length + tally.not_guilty.length;
  const guiltyShare = total ? tally.guilty.length / total : 0;
  return (
    <li className="rounded-lg border border-slate-800 bg-slate-900/30 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-slate-100">{titleCase(tally.charge)}</span>
        <Badge className={OUTCOME_STYLES[tally.outcome]}>
          {verdictLabel(tally.outcome)}
        </Badge>
        {tally.unanimous && <Badge>Unanimous</Badge>}
        <span className="ms-auto text-xs text-slate-500">
          agreement {percent(tally.agreement)}
          {before &&
            before.agreement !== tally.agreement &&
            ` (was ${percent(before.agreement)})`}
        </span>
      </div>
      <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-slate-800">
        <span
          className="bg-rose-500/70"
          style={{ width: `${guiltyShare * 100}%` }}
        />
        <span className="flex-1 bg-emerald-500/70" />
      </div>
      <div className="mt-1.5 flex flex-wrap justify-between gap-2 text-xs">
        <span className="text-rose-300">
          Guilty: {tally.guilty.map(agentLabel).join(", ") || "none"}
        </span>
        <span className="text-emerald-300">
          Not guilty: {tally.not_guilty.map(agentLabel).join(", ") || "none"}
        </span>
      </div>
    </li>
  );
}

function JurorCard({
  independent,
  after,
}: {
  independent: JurorDecision;
  after?: JurorDecision;
}) {
  const current = after ?? independent;
  const changed = after?.changed_charges ?? [];
  return (
    <article className="rounded-lg border border-violet-500/20 bg-slate-900/30 p-3">
      <header className="flex flex-wrap items-center gap-2">
        <span aria-hidden>👤</span>
        <span className="text-sm font-medium text-violet-200">
          {agentLabel(independent.juror_id)}
        </span>
        {changed.length > 0 && (
          <Badge className="border-violet-500/40 bg-violet-500/10 text-violet-200">
            changed on {changed.map(titleCase).join(", ")}
          </Badge>
        )}
        <span className="ms-auto flex items-center gap-1.5 text-xs text-slate-500">
          confidence
          <Meter value={current.output.confidence} tone="slate" />
          {percent(current.output.confidence)}
        </span>
      </header>

      <ul className="mt-2 space-y-2">
        {current.output.charge_verdicts.map((verdict) => {
          const earlier = independent.output.charge_verdicts.find(
            (row) => row.charge === verdict.charge,
          );
          return (
            <li key={verdict.charge} className="text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-slate-300">
                  {titleCase(verdict.charge)}
                </span>
                <Badge className={OUTCOME_STYLES[verdict.verdict]}>
                  {verdictLabel(verdict.verdict)}
                </Badge>
                {earlier && earlier.verdict !== verdict.verdict && (
                  <span className="text-xs text-violet-300">
                    was {verdictLabel(earlier.verdict)} on their own
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-xs text-slate-400">
                {verdict.reasoning}
              </p>
              <div className="mt-1 flex flex-wrap gap-2">
                <IdList
                  ids={[
                    ...verdict.evidence_ids,
                    ...verdict.witness_ids,
                    ...verdict.rule_ids,
                  ]}
                />
              </div>
            </li>
          );
        })}
      </ul>

      {current.output.uncertainties.length > 0 && (
        <div className={cx("mt-2 border-t border-slate-800 pt-2")}>
          <p className="text-xs text-slate-500">Left unresolved</p>
          <ul className="mt-0.5 space-y-0.5 text-xs text-amber-200/80">
            {current.output.uncertainties.map((item) => (
              <li key={item}>· {item}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
