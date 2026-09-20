"use client";

/** Case details: the record a trial will be argued from, and how to start one */

import Link from "next/link";
import { useParams } from "next/navigation";

import {
  CaseHeadline,
  EvidenceList,
  FactsList,
  LawCard,
  RuleEvaluationList,
  WitnessList,
} from "@/components/CaseRecord";
import { Loading, Problem } from "@/components/Problem";
import { SimulationForm } from "@/components/SimulationForm";
import { Tabs } from "@/components/Tabs";
import { Card } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { getCase, listRules } from "@/lib/api";

export default function CasePage() {
  const params = useParams<{ caseId: string }>();
  const caseId = params.caseId;
  const detail = useApi(() => getCase(caseId), [caseId]);
  const rules = useApi(listRules, []);

  if (detail.error) {
    return <Problem error={detail.error} retry={detail.reload} />;
  }
  if (!detail.data) {
    return <Loading what="the case" />;
  }

  const { case: record, rule_evaluation, evidence_provenance } = detail.data;
  const applicable = (rules.data ?? []).filter((rule) =>
    record.applicable_laws.includes(rule.rule_id),
  );

  return (
    <div className="space-y-6">
      <Link href="/" className="text-xs text-slate-500 hover:text-slate-300">
        ← All cases
      </Link>

      <CaseHeadline record={record} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <Card title="The record">
          <Tabs
            tabs={[
              {
                id: "facts",
                label: "Facts",
                badge: record.facts.length,
                content: <FactsList facts={record.facts} />,
              },
              {
                id: "evidence",
                label: "Evidence",
                badge: record.evidence.length,
                content: (
                  <EvidenceList
                    evidence={record.evidence}
                    provenance={evidence_provenance}
                  />
                ),
              },
              {
                id: "witnesses",
                label: "Witnesses",
                badge: record.witnesses.length,
                content: (
                  <WitnessList
                    witnesses={record.witnesses}
                    assessments={rule_evaluation.witness_assessments}
                  />
                ),
              },
              {
                id: "laws",
                label: "Laws",
                badge: record.applicable_laws.length,
                content: applicable.length ? (
                  <ul className="space-y-2">
                    {applicable.map((rule) => (
                      <LawCard key={rule.rule_id} rule={rule} />
                    ))}
                  </ul>
                ) : (
                  <Loading what="the legal rules" />
                ),
              },
              {
                id: "engine",
                label: "Rule engine",
                badge: rule_evaluation.rule_evaluations.length,
                content: <RuleEvaluationList evaluation={rule_evaluation} />,
              },
            ]}
          />
        </Card>

        <div className="space-y-6">
          <Card
            title="Run a simulation"
            subtitle={`${detail.data.bindings} element bindings link this record to the law`}
          >
            <SimulationForm caseId={caseId} runnable={detail.data.runnable} />
          </Card>

          <Card title="Before the trial">
            <p className="text-sm text-slate-400">
              The rule engine has already evaluated this record against every
              applicable law. The agents argue the case, but they cannot change
              what the engine computed - and every ID they cite is checked
              against the record above.
            </p>
            <dl className="mt-3 space-y-2 text-sm">
              {rule_evaluation.rule_evaluations
                .filter((rule) => record.applicable_laws.includes(rule.rule_id))
                .slice(0, 6)
                .map((rule) => (
                  <div
                    key={`${rule.rule_id}-${rule.subject}`}
                    className="flex items-baseline justify-between gap-3"
                  >
                    <dt className="text-slate-400">
                      {rule.rule_id} · {rule.subject}
                    </dt>
                    <dd className="text-slate-200">
                      {rule.status.replace("_", " ")}
                    </dd>
                  </div>
                ))}
            </dl>
          </Card>
        </div>
      </div>
    </div>
  );
}
