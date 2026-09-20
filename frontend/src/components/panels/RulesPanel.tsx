/**
 * Legal rules panel: the laws the agents actually cited, and what the rule
 * engine computed about them.
 *
 * The citation counts come from the arguments and verdicts themselves, so a
 * law nobody relied on is visibly separate from one the case turned on.
 */

import { agentLabel } from "@/lib/court";
import type { CaseEvaluation, RuleDetail, TrialRun } from "@/lib/types";
import { LawCard, RuleEvaluationCard } from "@/components/CaseRecord";
import { Empty } from "@/components/ui";

/** Who cited which law, across every part of the trial */
export function citationsByRule(run: TrialRun): Map<string, Set<string>> {
  const cited = new Map<string, Set<string>>();
  const add = (ruleId: string, agentId: string) => {
    const who = cited.get(ruleId) ?? new Set<string>();
    who.add(agentLabel(agentId));
    cited.set(ruleId, who);
  };

  for (const turn of run.turns) {
    for (const argument of turn.arguments) {
      for (const ruleId of argument.law_ids) add(ruleId, argument.agent_id);
    }
  }
  for (const decision of [...run.jury_independent, ...run.jury_deliberation]) {
    for (const verdict of decision.output.charge_verdicts) {
      for (const ruleId of verdict.rule_ids) add(ruleId, decision.juror_id);
    }
  }
  for (const rule of run.judgment.decision.applicable_rules) {
    add(rule.rule_id, "judge_agent");
  }
  for (const decision of run.judgment.decision.charge_decisions) {
    add(decision.rule_id, "judge_agent");
    for (const defense of decision.defenses_considered) {
      add(defense.rule_id, "judge_agent");
    }
  }
  return cited;
}

export function RulesPanel({
  run,
  rules,
  evaluation,
}: {
  run: TrialRun | null;
  rules: RuleDetail[];
  evaluation: CaseEvaluation;
}) {
  const cited = run ? citationsByRule(run) : new Map<string, Set<string>>();
  const referenced = rules.filter((rule) => cited.has(rule.rule_id));
  const others = rules.filter((rule) => !cited.has(rule.rule_id));

  return (
    <div className="space-y-5">
      <section>
        <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
          Referenced by the agents
        </h3>
        {referenced.length === 0 ? (
          <Empty>No law has been cited yet.</Empty>
        ) : (
          <ul className="space-y-2">
            {referenced.map((rule) => (
              <LawCard
                key={rule.rule_id}
                rule={rule}
                citedBy={[...(cited.get(rule.rule_id) ?? [])]}
              />
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
          What the rule engine computed
        </h3>
        <p className="mb-2 text-xs text-slate-500">
          Deterministic: the engine weighs the facts and evidence bound to each
          element. No agent can change these.
        </p>
        <ul className="space-y-2">
          {evaluation.rule_evaluations.map((rule) => (
            <RuleEvaluationCard
              key={`${rule.rule_id}-${rule.subject}`}
              rule={rule}
            />
          ))}
        </ul>
      </section>

      {others.length > 0 && (
        <details className="rounded-lg border border-slate-800 bg-slate-900/20 p-3">
          <summary className="cursor-pointer text-sm text-slate-400">
            The rest of the law of Arandia ({others.length})
          </summary>
          <ul className="mt-3 space-y-2">
            {others.map((rule) => (
              <LawCard key={rule.rule_id} rule={rule} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
