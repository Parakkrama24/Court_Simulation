"use client";

/**
 * Live simulation: the courtroom, the timeline, the events as they arrive, and
 * every panel the spec asks for.
 *
 * While a run is going, the only truth is the event stream - the panels that
 * need the full text of an argument say so and fill in when the run ends,
 * rather than inventing a placeholder for it.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo } from "react";

import { Courtroom } from "@/components/Courtroom";
import { LiveFeed } from "@/components/LiveFeed";
import { Loading, Problem } from "@/components/Problem";
import { Tabs } from "@/components/Tabs";
import { Timeline } from "@/components/Timeline";
import { AuditPanel } from "@/components/panels/AuditPanel";
import { DebatePanel } from "@/components/panels/DebatePanel";
import { EvidencePanel } from "@/components/panels/EvidencePanel";
import { JudgeDecisionPanel } from "@/components/panels/JudgeDecisionPanel";
import { JuryPanel } from "@/components/panels/JuryPanel";
import { RulesPanel } from "@/components/panels/RulesPanel";
import { Badge, Card, Empty, IdList, cx } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { useRunStream } from "@/hooks/useRunStream";
import { getCase, listRules } from "@/lib/api";
import {
  STATUS_STYLES,
  agentLabel,
  duration,
  stageLabel,
  titleCase,
} from "@/lib/court";
import { analysisOf, isTrialRun, judgmentOf } from "@/lib/result";
import { deriveCourt, progress, timeline } from "@/lib/runState";

export default function RunPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const { run, events, status, transport, error } = useRunStream(runId);

  const caseId = run?.case_id;
  const detail = useApi(
    () => (caseId ? getCase(caseId) : Promise.resolve(null)),
    [caseId],
  );
  const rules = useApi(listRules, []);

  const court = useMemo(() => deriveCourt(events, status), [events, status]);
  const live = status === "queued" || status === "running";

  if (error && !run) {
    return <Problem error={error} />;
  }
  if (!run) {
    return <Loading what="the simulation" />;
  }

  const result = run.result;
  const trial = isTrialRun(result) ? result : null;
  const record = detail.data?.case ?? null;
  const evaluation = detail.data?.rule_evaluation ?? null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href={`/cases/${run.case_id}`}
          className="text-xs text-slate-500 hover:text-slate-300"
        >
          ← {run.case_id}
        </Link>
        <Badge className={STATUS_STYLES[status]}>{titleCase(status)}</Badge>
        <Badge>{run.mode}</Badge>
        <span className="font-mono text-xs text-slate-500">{run.run_id}</span>
        <span className="text-xs text-slate-500">
          {run.started_at && duration(run.started_at, run.finished_at)}
          {run.usage?.calls ? ` · ${run.usage.calls} model calls` : ""}
          {run.usage?.input_tokens
            ? ` · ${run.usage.input_tokens + run.usage.output_tokens} tokens`
            : ""}
        </span>
        <span className="ms-auto text-xs text-slate-600">
          {live
            ? transport === "stream"
              ? "streaming (SSE)"
              : transport === "polling"
                ? "polling"
                : ""
            : "finished"}
        </span>
      </div>

      {run.error && (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 text-sm text-rose-200">
          The run failed: {run.error}
        </p>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <Courtroom
            state={court}
            caseTitle={record?.title ?? run.case_id}
            jurors={run.options.jurors}
          />

          <Card
            title="The hearing"
            subtitle={
              live
                ? "Panels fill in as the court reaches each stage"
                : `Completed at ${run.finished_at?.slice(11, 19) ?? ""}`
            }
          >
            <Tabs
              tabs={[
                {
                  id: "debate",
                  label: "Debate",
                  badge: trial
                    ? trial.turns.reduce((n, t) => n + t.arguments.length, 0)
                    : court.argumentsPresented.length,
                  content: trial ? (
                    <DebatePanel run={trial} />
                  ) : (
                    <LiveArguments court={court} live={live} />
                  ),
                },
                {
                  id: "evidence",
                  label: "Evidence",
                  badge: record?.evidence.length ?? 0,
                  content: record ? (
                    <EvidencePanel
                      record={record}
                      analysis={analysisOf(result)}
                      provenance={detail.data?.evidence_provenance}
                    />
                  ) : (
                    <Loading what="the evidence" />
                  ),
                },
                {
                  id: "rules",
                  label: "Legal rules",
                  content: evaluation ? (
                    <RulesPanel
                      run={trial}
                      rules={rules.data ?? []}
                      evaluation={evaluation}
                    />
                  ) : (
                    <Loading what="the legal rules" />
                  ),
                },
                {
                  id: "jury",
                  label: "Jury",
                  badge: run.options.jury ? run.options.jurors : 0,
                  content: trial ? (
                    <JuryPanel
                      independent={trial.jury_independent}
                      deliberation={trial.jury_deliberation}
                      result={trial.jury_result}
                    />
                  ) : (
                    <LiveVotes court={court} live={live} />
                  ),
                },
                {
                  id: "judge",
                  label: "Judge decision",
                  content: (
                    <JudgeDecisionPanel
                      judgment={judgmentOf(result)}
                      agreement={trial?.judge_jury_agreement}
                    />
                  ),
                },
                {
                  id: "audit",
                  label: "Audit",
                  badge: trial?.audit?.findings.length,
                  content: <AuditPanel audit={trial?.audit ?? null} />,
                },
              ]}
            />
          </Card>
        </div>

        <div className="space-y-5">
          <Card
            title="Courtroom timeline"
            subtitle={`${Math.round(progress(court) * 100)}% of the procedure`}
          >
            <Timeline stages={timeline(court)} />
          </Card>

          <Card title="Live simulation">
            <LiveFeed events={events} live={live} />
          </Card>

          <Card title="How this run was configured">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
              {[
                ["Mode", run.options.mode],
                ["Evidence Agent", yesNo(run.options.evidence)],
                ["Cross-examination", yesNo(run.options.cross_examination)],
                [
                  "Judge questions",
                  run.options.judge_questions
                    ? `up to ${run.options.question_rounds} round(s)`
                    : "no",
                ],
                [
                  "Jury",
                  run.options.jury
                    ? `${run.options.jurors} jurors, ${run.options.jury_rule}`
                    : "no",
                ],
                ["Deliberation", yesNo(run.options.deliberation)],
                [
                  "Audit",
                  run.options.audit
                    ? run.options.audit_agent
                      ? "checks + auditor agent"
                      : "deterministic checks"
                    : "no",
                ],
                ["Attempts per agent", String(run.options.max_attempts)],
                ["Provider", run.options.provider ?? "server default"],
                ["Model", run.options.model ?? "server default"],
              ].map(([label, value]) => (
                <div key={label} className="contents">
                  <dt className="text-slate-500">{label}</dt>
                  <dd className="text-slate-300">{value}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>
      </div>
    </div>
  );
}

const yesNo = (value: boolean) => (value ? "yes" : "no");

/** While the trial runs, the events name the arguments but not their text */
function LiveArguments({
  court,
  live,
}: {
  court: ReturnType<typeof deriveCourt>;
  live: boolean;
}) {
  if (court.argumentsPresented.length === 0) {
    return (
      <Empty>
        {live ? "No argument has been presented yet." : "No arguments."}
      </Empty>
    );
  }
  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        The stream reports each argument as it is accepted. The full text
        arrives with the finished run.
      </p>
      <ul className="space-y-1.5">
        {court.argumentsPresented.map((argument) => (
          <li
            key={argument.argumentId}
            className={cx(
              "flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/30 px-3 py-2",
              court.unsupported.includes(argument.argumentId) &&
                "border-rose-500/30",
            )}
          >
            <IdList ids={[argument.argumentId]} />
            <span className="text-xs text-slate-400">
              {agentLabel(argument.agentId)}
            </span>
            <span className="text-xs text-slate-600">
              {stageLabel(argument.stage)}
            </span>
            {court.unsupported.includes(argument.argumentId) && (
              <Badge className="ms-auto border-rose-500/40 bg-rose-500/10 text-rose-300">
                the evidence review found this unsupported
              </Badge>
            )}
          </li>
        ))}
      </ul>
      {court.questionsAsked.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs tracking-wide text-slate-500 uppercase">
            The judge has asked
          </h3>
          <ul className="space-y-1">
            {court.questionsAsked.map((question) => (
              <li
                key={question.questionId}
                className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-1.5 text-xs"
              >
                <IdList ids={[question.questionId]} />
                <span className="text-slate-400">
                  to {agentLabel(question.addressedTo)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function LiveVotes({
  court,
  live,
}: {
  court: ReturnType<typeof deriveCourt>;
  live: boolean;
}) {
  if (court.votes.length === 0) {
    return (
      <Empty>
        {live ? "The jury has not voted yet." : "No jury sat in this run."}
      </Empty>
    );
  }
  return (
    <ul className="space-y-1.5">
      {court.votes.map((vote, index) => (
        <li
          key={`${vote.jurorId}-${vote.round}-${index}`}
          className="flex flex-wrap items-center gap-2 rounded-lg border border-violet-500/20 bg-slate-900/30 px-3 py-2 text-sm"
        >
          <span className="text-violet-200">{agentLabel(vote.jurorId)}</span>
          <Badge>{vote.round}</Badge>
          <span className="text-slate-300">{vote.decision}</span>
        </li>
      ))}
      {court.juryVerdict && (
        <li className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-3 py-2 text-sm text-violet-100">
          Verdict:{" "}
          {Object.entries(court.juryVerdict)
            .map(([charge, outcome]) => `${titleCase(charge)} ${outcome}`)
            .join("; ")}
        </li>
      )}
    </ul>
  );
}
