/**
 * The case record: facts, evidence, witnesses, and the legal rules.
 *
 * These are the authoritative parts of a case - nothing here comes from an
 * agent - so they render the same on the case page and inside a running
 * trial's panels.
 */

import { percent, titleCase } from "@/lib/court";
import type {
  Case,
  CaseEvaluation,
  Evidence,
  EvidenceProvenance,
  Fact,
  RuleDetail,
  RuleEvaluation,
  Witness,
  WitnessAssessment,
} from "@/lib/types";
import { Badge, Empty, IdChip, IdList, Meter, cx } from "@/components/ui";

const FACT_STYLES: Record<string, string> = {
  established: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  disputed: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  unknown: "border-slate-600/50 bg-slate-800/60 text-slate-400",
};

export function FactsList({ facts }: { facts: Fact[] }) {
  if (facts.length === 0) return <Empty>No facts on the record.</Empty>;
  return (
    <ul className="space-y-2">
      {facts.map((fact) => (
        <li
          key={fact.fact_id}
          className="rounded-lg border border-slate-800 bg-slate-900/30 p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <IdChip id={fact.fact_id} />
            <Badge className={FACT_STYLES[fact.status]}>
              {titleCase(fact.status)}
            </Badge>
            <span className="text-xs text-slate-500">
              source: {fact.source}
            </span>
          </div>
          <p className="mt-1.5 text-sm text-slate-200">{fact.description}</p>
        </li>
      ))}
    </ul>
  );
}

export function EvidenceList({
  evidence,
  provenance = [],
}: {
  evidence: Evidence[];
  provenance?: EvidenceProvenance[];
}) {
  if (evidence.length === 0) return <Empty>No evidence on the record.</Empty>;
  const trail = new Map(provenance.map((p) => [p.evidence_id, p]));
  return (
    <ul className="space-y-2">
      {evidence.map((item) => {
        const chain = trail.get(item.evidence_id);
        return (
          <li
            key={item.evidence_id}
            className="rounded-lg border border-slate-800 bg-slate-900/30 p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <IdChip id={item.evidence_id} />
              <Badge>{titleCase(item.type)}</Badge>
              <span className="ms-auto flex items-center gap-2 text-xs text-slate-400">
                reliability
                <Meter
                  value={item.reliability}
                  tone={
                    item.reliability >= 0.8
                      ? "emerald"
                      : item.reliability >= 0.5
                        ? "amber"
                        : "rose"
                  }
                />
                {percent(item.reliability)}
              </span>
            </div>
            <p className="mt-1.5 text-sm text-slate-200">{item.description}</p>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <IdList label="supports" ids={item.supports} />
              <IdList label="contradicts" ids={item.contradicts} />
              <span className="text-xs text-slate-500">
                source: {item.source}
              </span>
            </div>
            {chain && (
              <p className="mt-2 border-t border-slate-800 pt-2 text-xs text-slate-500">
                Chain of custody: {chain.handled_by ?? "not recorded"}
                {chain.date && ` · ${chain.date}`}
                {chain.witness_id && ` · witness ${chain.witness_id}`}
                {chain.gaps.length > 0 && (
                  <span className="text-amber-300">
                    {" "}
                    · gaps: {chain.gaps.join("; ")}
                  </span>
                )}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function WitnessList({
  witnesses,
  assessments = [],
}: {
  witnesses: Witness[];
  assessments?: WitnessAssessment[];
}) {
  if (witnesses.length === 0) return <Empty>No witnesses.</Empty>;
  const scored = new Map(assessments.map((a) => [a.witness_id, a]));
  return (
    <ul className="space-y-2">
      {witnesses.map((witness) => {
        const assessment = scored.get(witness.witness_id);
        return (
          <li
            key={witness.witness_id}
            className="rounded-lg border border-slate-800 bg-slate-900/30 p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <IdChip id={witness.witness_id} />
              <span className="text-sm font-medium text-slate-100">
                {witness.name}
              </span>
              {assessment && (
                <span className="ms-auto flex items-center gap-2 text-xs text-slate-400">
                  rule engine score
                  <Meter
                    value={assessment.reliability_score}
                    tone={
                      assessment.reliability_score >= 0.8
                        ? "emerald"
                        : assessment.reliability_score >= 0.5
                          ? "amber"
                          : "rose"
                    }
                  />
                  {percent(assessment.reliability_score)}
                </span>
              )}
            </div>
            <p className="mt-1.5 text-sm text-slate-300 italic">
              “{witness.statement}”
            </p>
            {assessment && (
              <div className="mt-2 grid gap-2 text-xs sm:grid-cols-2">
                <div>
                  <p className="text-slate-500">Supports reliability</p>
                  <ul className="mt-0.5 space-y-0.5 text-emerald-300">
                    {assessment.positive_factors.map((factor) => (
                      <li key={factor}>· {factor}</li>
                    ))}
                    {assessment.positive_factors.length === 0 && (
                      <li className="text-slate-500">· none recorded</li>
                    )}
                  </ul>
                </div>
                <div>
                  <p className="text-slate-500">Grounds for challenge</p>
                  <ul className="mt-0.5 space-y-0.5 text-amber-300">
                    {assessment.challenge_grounds.map((ground) => (
                      <li key={ground}>· {ground}</li>
                    ))}
                    {assessment.challenge_grounds.length === 0 && (
                      <li className="text-slate-500">· none</li>
                    )}
                  </ul>
                </div>
              </div>
            )}
            <IdList
              label="related evidence"
              ids={witness.related_evidence}
              empty=""
            />
          </li>
        );
      })}
    </ul>
  );
}

const CATEGORY_STYLES: Record<string, string> = {
  offense: "border-rose-500/30 bg-rose-500/10 text-rose-300",
  defense: "border-sky-500/30 bg-sky-500/10 text-sky-300",
  principle: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  evidence_rule: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  procedure: "border-slate-600/50 bg-slate-800/60 text-slate-300",
};

export function LawCard({
  rule,
  citedBy = [],
}: {
  rule: RuleDetail;
  citedBy?: string[];
}) {
  return (
    <li className="rounded-lg border border-slate-800 bg-slate-900/30 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <IdChip id={rule.rule_id} />
        <span className="text-sm font-medium text-slate-100">{rule.name}</span>
        <Badge className={CATEGORY_STYLES[rule.category]}>
          {titleCase(rule.category)}
        </Badge>
        {citedBy.length > 0 && (
          <Badge
            className="ms-auto border-amber-500/30 bg-amber-500/10 text-amber-200"
            title={citedBy.join(", ")}
          >
            cited by {citedBy.join(", ")}
          </Badge>
        )}
      </div>
      <p className="mt-1.5 text-sm text-slate-300">{rule.description}</p>
      {rule.conditions.length > 0 && (
        <ol className="mt-2 space-y-1">
          {rule.conditions.map((condition) => (
            <li key={condition.id} className="flex gap-2 text-xs text-slate-400">
              <span className="font-mono text-slate-500">{condition.id}</span>
              <span>
                {condition.description}
                {!condition.required && " (optional)"}
                {condition.depends_on_rule && (
                  <span className="text-slate-500">
                    {" "}
                    · depends on {condition.depends_on_rule}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
      <p className="mt-2 text-xs text-slate-500">Effect: {rule.effect}</p>
    </li>
  );
}

const RULE_STATUS_STYLES: Record<string, string> = {
  satisfied: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  not_satisfied: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  indeterminate: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  not_applicable: "border-slate-600/50 bg-slate-800/60 text-slate-400",
};

const CONDITION_STATUS_STYLES: Record<string, string> = {
  satisfied: "text-emerald-300",
  unsatisfied: "text-rose-300",
  contested: "text-amber-300",
  indeterminate: "text-slate-400",
};

/**
 * What the rule engine computed, element by element. This is deterministic:
 * no agent decides any of it, which is why it is shown next to what the
 * agents argued.
 */
export function RuleEvaluationList({
  evaluation,
}: {
  evaluation: CaseEvaluation;
}) {
  if (evaluation.rule_evaluations.length === 0) {
    return (
      <Empty>
        The rule engine has nothing to evaluate: this case has no element
        bindings.
      </Empty>
    );
  }
  return (
    <ul className="space-y-2">
      {evaluation.rule_evaluations.map((rule) => (
        <RuleEvaluationCard
          key={`${rule.rule_id}-${rule.subject}`}
          rule={rule}
        />
      ))}
    </ul>
  );
}

export function RuleEvaluationCard({ rule }: { rule: RuleEvaluation }) {
  return (
    <li className="rounded-lg border border-slate-800 bg-slate-900/30 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <IdChip id={rule.rule_id} />
        <span className="text-sm text-slate-100">{rule.rule_name}</span>
        <span className="text-xs text-slate-500">· {rule.subject}</span>
        <Badge className={cx("ms-auto", RULE_STATUS_STYLES[rule.status])}>
          {titleCase(rule.status)}
        </Badge>
      </div>
      <ul className="mt-2 space-y-1.5">
        {rule.conditions.map((condition) => (
          <li key={condition.condition_id} className="text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-slate-500">
                {condition.condition_id}
              </span>
              <span className="text-slate-300">{condition.description}</span>
              <span
                className={cx(
                  "ms-auto",
                  CONDITION_STATUS_STYLES[condition.status],
                )}
              >
                {titleCase(condition.status)}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 ps-6 text-slate-500">
              <span>support</span>
              <Meter value={condition.support_strength} tone="emerald" />
              <span>{percent(condition.support_strength)}</span>
              <span className="ms-2">contradiction</span>
              <Meter value={condition.contradiction_strength} tone="rose" />
              <span>{percent(condition.contradiction_strength)}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-2 ps-6">
              <IdList
                label="for"
                ids={[
                  ...condition.supporting_fact_ids,
                  ...condition.supporting_evidence_ids,
                ]}
              />
              <IdList
                label="against"
                ids={[
                  ...condition.contradicting_fact_ids,
                  ...condition.contradicting_evidence_ids,
                ]}
              />
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 border-t border-slate-800 pt-2 text-xs text-slate-400">
        {rule.reasoning}
      </p>
    </li>
  );
}

export function CaseHeadline({ record }: { record: Case }) {
  return (
    <div>
      <p className="font-mono text-xs text-slate-500">{record.case_id}</p>
      <h1 className="font-[family-name:var(--font-display)] text-2xl text-slate-100">
        {record.title}
      </h1>
      <p className="mt-1 text-sm text-slate-400">{record.description}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-500">{record.prosecution}</span>
        <span className="text-slate-600">v.</span>
        <span className="text-slate-200">{record.defendant}</span>
        {record.charges.map((charge) => (
          <Badge
            key={charge}
            className="border-rose-500/30 bg-rose-500/10 text-rose-300"
          >
            {titleCase(charge)}
          </Badge>
        ))}
        <Badge className="border-slate-600/50 bg-slate-800/60 text-slate-400">
          {titleCase(record.case_type)} · {record.jurisdiction}
        </Badge>
      </div>
    </div>
  );
}
