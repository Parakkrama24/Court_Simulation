"use client";

/** The legal rules of Arandia: the whole fictional statute book */

import { LawCard } from "@/components/CaseRecord";
import { Loading, Problem } from "@/components/Problem";
import { Tabs } from "@/components/Tabs";
import { Card } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { listRules } from "@/lib/api";
import { titleCase } from "@/lib/court";
import type { LegalCategory } from "@/lib/types";

const ORDER: LegalCategory[] = [
  "offense",
  "defense",
  "principle",
  "evidence_rule",
  "procedure",
];

export default function RulesPage() {
  const rules = useApi(listRules, []);

  if (rules.error) return <Problem error={rules.error} retry={rules.reload} />;
  if (!rules.data) return <Loading what="the legal rules" />;

  const categories = ORDER.filter((category) =>
    rules.data!.some((rule) => rule.category === category),
  );

  return (
    <Card
      title="The law of Arandia"
      subtitle="Fictional, structured, and authoritative: the rule engine reads exactly these"
    >
      <Tabs
        tabs={[
          {
            id: "all",
            label: "All",
            badge: rules.data.length,
            content: (
              <ul className="space-y-2">
                {rules.data.map((rule) => (
                  <LawCard key={rule.rule_id} rule={rule} />
                ))}
              </ul>
            ),
          },
          ...categories.map((category) => {
            const inCategory = rules.data!.filter(
              (rule) => rule.category === category,
            );
            return {
              id: category,
              label: titleCase(category),
              badge: inCategory.length,
              content: (
                <ul className="space-y-2">
                  {inCategory.map((rule) => (
                    <LawCard key={rule.rule_id} rule={rule} />
                  ))}
                </ul>
              ),
            };
          }),
        ]}
      />
    </Card>
  );
}
