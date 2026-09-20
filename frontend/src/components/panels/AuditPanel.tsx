/**
 * Audit panel: what the Legal Process Auditor found.
 *
 * Spec section 20 asks for hallucinations, unsupported claims, procedural
 * violations, and evidence violations, which are the auditor's own
 * categories. Each finding says whether a deterministic check or the auditor
 * agent raised it - the checks are the ones that cannot be talked out of a
 * finding.
 */

import { agentLabel, stageLabel, titleCase } from "@/lib/court";
import type {
  AuditFinding,
  FindingCategory,
  FindingSeverity,
  ProcessAudit,
} from "@/lib/types";
import { Badge, Empty, IdList, cx } from "@/components/ui";

const SEVERITY_STYLES: Record<FindingSeverity, string> = {
  critical: "border-rose-500/50 bg-rose-500/10 text-rose-200",
  major: "border-orange-500/50 bg-orange-500/10 text-orange-200",
  minor: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  info: "border-slate-600/50 bg-slate-800/60 text-slate-300",
};

const STATUS_STYLES: Record<string, string> = {
  clean: "border-emerald-500/50 bg-emerald-500/10 text-emerald-200",
  minor_issues: "border-amber-500/50 bg-amber-500/10 text-amber-200",
  major_issues: "border-orange-500/50 bg-orange-500/10 text-orange-200",
  critical: "border-rose-500/50 bg-rose-500/10 text-rose-200",
};

const GROUPS: { category: FindingCategory; title: string; blurb: string }[] = [
  {
    category: "hallucination",
    title: "Hallucinations",
    blurb: "IDs or facts an agent invented that are not on the record",
  },
  {
    category: "evidence",
    title: "Evidence violations",
    blurb: "Claims the cited evidence does not support",
  },
  {
    category: "procedural",
    title: "Procedural violations",
    blurb: "Stages skipped, out of order, or missing a required step",
  },
  {
    category: "legal",
    title: "Legal violations",
    blurb: "Rules applied against what the rule engine computed",
  },
  {
    category: "reasoning",
    title: "Reasoning issues",
    blurb: "Unsupported or circular steps between findings and decision",
  },
];

export function AuditPanel({ audit }: { audit: ProcessAudit | null }) {
  if (!audit) {
    return <Empty>This simulation was not audited.</Empty>;
  }
  const { report, findings } = audit;
  const status = report.metadata.overall_status;

  return (
    <div className="space-y-5">
      <section
        className={cx(
          "rounded-xl border p-4",
          STATUS_STYLES[status] ?? STATUS_STYLES.clean,
        )}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span aria-hidden className="text-xl">
            📋
          </span>
          <h3 className="font-[family-name:var(--font-display)] text-lg">
            {titleCase(status)}
          </h3>
          <span className="ms-auto font-mono text-xs opacity-70">
            {report.audit_id}
          </span>
        </div>
        <p className="mt-2 text-sm text-slate-200">{report.final_assessment}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {(
            Object.entries(report.metadata.severity_counts) as [
              FindingSeverity,
              number,
            ][]
          ).map(([severity, count]) => (
            <Badge key={severity} className={SEVERITY_STYLES[severity]}>
              {count} {severity}
            </Badge>
          ))}
          <Badge>
            {report.metadata.sources.deterministic} from checks ·{" "}
            {report.metadata.sources.auditor_agent} from the auditor agent
          </Badge>
          {report.metadata.deterministic_only && (
            <Badge title="No auditor agent ran: every finding here is a deterministic check">
              Deterministic only
            </Badge>
          )}
        </div>
      </section>

      {(report.metadata.decision_chain ?? []).length > 0 && (
        <section>
          <h3 className="mb-2 text-xs tracking-wide text-slate-500 uppercase">
            The decision chain
          </h3>
          <ul className="grid gap-2 sm:grid-cols-2">
            {report.metadata.decision_chain.map((link) => (
              <li
                key={link.link}
                className="rounded-lg border border-slate-800 bg-slate-900/30 p-3 text-sm"
              >
                <div className="flex items-center gap-2">
                  <span className="text-slate-200">
                    {titleCase(link.link.replace(/_to_/g, " → "))}
                  </span>
                  <Badge
                    className={cx(
                      "ms-auto",
                      link.rating === "sound"
                        ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                        : "border-amber-500/40 bg-amber-500/10 text-amber-300",
                    )}
                  >
                    {titleCase(link.rating)}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-slate-400">{link.note}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {GROUPS.map((group) => {
        const rows = findings.filter(
          (finding) => finding.category === group.category,
        );
        return (
          <section key={group.category}>
            <h3 className="mb-1 flex items-center gap-2 text-xs tracking-wide text-slate-500 uppercase">
              {group.title}
              <span className="text-slate-600">({rows.length})</span>
            </h3>
            <p className="mb-2 text-xs text-slate-600">{group.blurb}</p>
            {rows.length === 0 ? (
              <p className="rounded-lg border border-slate-800 bg-slate-900/20 px-3 py-2 text-sm text-slate-500">
                None found.
              </p>
            ) : (
              <ul className="space-y-2">
                {rows.map((finding) => (
                  <FindingCard key={finding.finding_id} finding={finding} />
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}

function FindingCard({ finding }: { finding: AuditFinding }) {
  return (
    <li
      className={cx(
        "rounded-lg border bg-slate-900/30 p-3",
        SEVERITY_STYLES[finding.severity],
      )}
    >
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono text-slate-500">{finding.finding_id}</span>
        <Badge className={SEVERITY_STYLES[finding.severity]}>
          {titleCase(finding.severity)}
        </Badge>
        <span className="text-slate-400">{finding.check}</span>
        {finding.agent_id && (
          <span className="text-slate-400">· {agentLabel(finding.agent_id)}</span>
        )}
        {finding.stage && (
          <span className="text-slate-500">· {stageLabel(finding.stage)}</span>
        )}
        <Badge className="ms-auto border-slate-700 bg-slate-800/60 text-slate-400">
          {finding.source === "deterministic" ? "check" : "auditor agent"}
        </Badge>
      </div>
      <p className="mt-1.5 text-sm text-slate-100">{finding.description}</p>
      {finding.references.length > 0 && (
        <div className="mt-1.5">
          <IdList label="about" ids={finding.references} />
        </div>
      )}
    </li>
  );
}
