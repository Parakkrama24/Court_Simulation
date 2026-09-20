/**
 * Judge decision: findings, applicable law, reasoning, and the verdict.
 *
 * The four are kept apart deliberately - spec section 7 requires a judgment
 * that separates what was found from what follows from it. Where the judge
 * and the rule engine disagree, the divergence is shown rather than hidden.
 */

import { percent, titleCase, verdictLabel } from "@/lib/court";
import type { JudgeResult } from "@/lib/types";
import { Badge, Empty, IdList, Meter, cx } from "@/components/ui";

const DECISION_STYLES: Record<string, string> = {
  guilty: "border-rose-500/40 bg-rose-500/10 text-rose-200",
  not_guilty: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
};

const ASSESSMENT_STYLES: Record<string, string> = {
  established: "text-emerald-300",
  not_established: "text-rose-300",
  partly_established: "text-amber-300",
};

export function JudgeDecisionPanel({
  judgment,
  agreement = [],
}: {
  judgment: JudgeResult | null;
  agreement?: { charge: string; judge: string; jury: string; agrees: boolean }[];
}) {
  if (!judgment) {
    return <Empty>The judge has not decided yet.</Empty>;
  }
  const { decision, verdict } = judgment;

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span aria-hidden className="text-xl">
            ⚖️
          </span>
          <h3 className="font-[family-name:var(--font-display)] text-lg text-amber-100">
            Verdict
          </h3>
          <span className="ms-auto flex items-center gap-1.5 text-xs text-slate-400">
            confidence
            <Meter value={verdict.confidence} tone="amber" />
            {percent(verdict.confidence)}
          </span>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {decision.charge_decisions.map((charge) => (
            <Badge
              key={charge.charge}
              className={cx("text-sm", DECISION_STYLES[charge.decision])}
            >
              {titleCase(charge.charge)}: {verdictLabel(charge.decision)}
            </Badge>
          ))}
        </div>
        <p className="mt-3 text-sm whitespace-pre-line text-slate-200">
          {verdict.reasoning}
        </p>
        {verdict.unresolved_questions.length > 0 && (
          <div className="mt-3 border-t border-amber-500/20 pt-2">
            <p className="text-xs text-slate-500">Left unresolved</p>
            <ul className="mt-0.5 text-xs text-amber-200/80">
              {verdict.unresolved_questions.map((question) => (
                <li key={question}>· {question}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {agreement.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
            Judge and jury
          </h3>
          <ul className="grid gap-2 sm:grid-cols-2">
            {agreement.map((row) => (
              <li
                key={row.charge}
                className={cx(
                  "rounded-lg border p-3 text-sm",
                  row.agrees
                    ? "border-slate-800 bg-slate-900/30"
                    : "border-amber-500/40 bg-amber-500/5",
                )}
              >
                <p className="text-slate-200">{titleCase(row.charge)}</p>
                <p className="mt-1 text-xs text-slate-400">
                  Judge {verdictLabel(row.judge)} · Jury{" "}
                  {verdictLabel(row.jury)}
                  {!row.agrees && (
                    <span className="text-amber-300"> · they differ</span>
                  )}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
          Findings of fact
        </h3>
        <ul className="space-y-2">
          {decision.established_facts.map((fact) => (
            <li
              key={fact.fact_id}
              className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <IdList ids={[fact.fact_id]} />
                <Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
                  Established
                </Badge>
                <IdList label="on" ids={fact.evidence_ids} />
              </div>
              <p className="mt-1.5 text-sm text-slate-200">{fact.finding}</p>
            </li>
          ))}
          {decision.disputed_facts.map((fact) => (
            <li
              key={fact.fact_id}
              className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <IdList ids={[fact.fact_id]} />
                <Badge className="border-amber-500/30 bg-amber-500/10 text-amber-300">
                  Disputed
                </Badge>
              </div>
              <p className="mt-1.5 text-sm text-slate-200">{fact.issue}</p>
              <p className="mt-1 text-sm text-slate-400">{fact.resolution}</p>
              <div className="mt-1.5 flex flex-wrap gap-3">
                <IdList label="for" ids={fact.supporting_evidence_ids} />
                <IdList label="against" ids={fact.contradicting_evidence_ids} />
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
          Applicable law
        </h3>
        <ul className="space-y-1.5">
          {decision.applicable_rules.map((rule) => (
            <li
              key={rule.rule_id}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/30 px-3 py-2 text-sm"
            >
              <IdList ids={[rule.rule_id]} />
              <span className="text-slate-300">{rule.relevance}</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
          Reasoning, element by element
        </h3>
        <p className="mb-3 text-sm text-slate-300">{decision.analysis}</p>
        <ul className="space-y-2">
          {decision.charge_decisions.map((charge) => (
            <li
              key={charge.charge}
              className="rounded-lg border border-slate-800 bg-slate-900/30 p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm text-slate-100">
                  {titleCase(charge.charge)}
                </span>
                <IdList ids={[charge.rule_id]} />
                <Badge className={DECISION_STYLES[charge.decision]}>
                  {verdictLabel(charge.decision)}
                </Badge>
                <span className="ms-auto text-xs text-slate-500">
                  {percent(charge.confidence)} confident
                </span>
              </div>
              <ul className="mt-2 space-y-1.5">
                {charge.elements.map((element) => (
                  <li key={element.condition_id} className="text-xs">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-slate-500">
                        {element.condition_id}
                      </span>
                      <span
                        className={
                          ASSESSMENT_STYLES[element.assessment] ??
                          "text-slate-400"
                        }
                      >
                        {titleCase(element.assessment)}
                      </span>
                      <IdList
                        ids={[...element.fact_ids, ...element.evidence_ids]}
                      />
                    </div>
                    <p className="mt-0.5 text-slate-400">{element.reasoning}</p>
                  </li>
                ))}
              </ul>
              {charge.defenses_considered.length > 0 && (
                <ul className="mt-2 border-t border-slate-800 pt-2">
                  {charge.defenses_considered.map((defense) => (
                    <li key={defense.rule_id} className="text-xs text-slate-400">
                      <span className="font-mono text-slate-500">
                        {defense.rule_id}
                      </span>{" "}
                      {titleCase(defense.assessment)} - {defense.reasoning}
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-sm text-slate-300">{charge.reasoning}</p>
            </li>
          ))}
        </ul>
      </section>

      {judgment.divergences.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
            Where the judge differs from the rule engine
          </h3>
          <ul className="space-y-1.5">
            {judgment.divergences.map((divergence, index) => (
              <li
                key={index}
                className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-sm text-amber-100"
              >
                {String(
                  divergence.description ?? JSON.stringify(divergence),
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
