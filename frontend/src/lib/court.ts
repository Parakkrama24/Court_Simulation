/**
 * The vocabulary of the courtroom: stages, agents, and the small formatting
 * helpers every panel shares.
 *
 * The stage list is the spec's section 14 procedure, in order, which is also
 * the order the backend runs it in.
 */

import type { CourtEvent, RunStatus } from "./types";

// ----------------------------------------------------------------- stages

export const STAGES = [
  "CASE_INITIALIZATION",
  "RULE_EVALUATION",
  "EVIDENCE_ANALYSIS",
  "PROSECUTION_OPENING",
  "DEFENSE_OPENING",
  "PROSECUTION_ARGUMENT",
  "DEFENSE_ARGUMENT",
  "CROSS_EXAMINATION",
  "EVIDENCE_REVIEW",
  "JUDGE_QUESTIONS",
  "PROSECUTION_REBUTTAL",
  "DEFENSE_REBUTTAL",
  "CLOSING_ARGUMENTS",
  "JURY_INDEPENDENT_DELIBERATION",
  "JURY_DELIBERATION",
  "JUDGE_DECISION",
  "LEGAL_PROCESS_AUDIT",
  "CASE_COMPLETE",
] as const;

export type Stage = (typeof STAGES)[number];

const STAGE_LABELS: Record<string, string> = {
  CASE_INITIALIZATION: "Case initialisation",
  RULE_EVALUATION: "Rule evaluation",
  EVIDENCE_ANALYSIS: "Evidence analysis",
  PROSECUTION_OPENING: "Prosecution opening",
  DEFENSE_OPENING: "Defense opening",
  PROSECUTION_ARGUMENT: "Prosecution argument",
  DEFENSE_ARGUMENT: "Defense argument",
  CROSS_EXAMINATION: "Cross-examination",
  EVIDENCE_REVIEW: "Evidence review",
  JUDGE_QUESTIONS: "Judge questions",
  PROSECUTION_REBUTTAL: "Prosecution rebuttal",
  DEFENSE_REBUTTAL: "Defense rebuttal",
  CLOSING_ARGUMENTS: "Closing arguments",
  JURY_INDEPENDENT_DELIBERATION: "Jury deliberates independently",
  JURY_DELIBERATION: "Jury deliberation",
  JUDGE_DECISION: "Judge decision",
  LEGAL_PROCESS_AUDIT: "Legal process audit",
  CASE_COMPLETE: "Case complete",
};

export const stageLabel = (stage: string): string =>
  STAGE_LABELS[stage] ?? titleCase(stage);

/** Which bench seat a stage belongs to, for highlighting the courtroom */
export const stageSide = (stage: string): Seat | null => {
  if (stage.startsWith("PROSECUTION")) return "prosecution";
  if (stage.startsWith("DEFENSE")) return "defense";
  if (stage.startsWith("JURY")) return "jury";
  if (stage.startsWith("EVIDENCE")) return "analyst";
  if (stage === "LEGAL_PROCESS_AUDIT") return "auditor";
  if (stage.startsWith("JUDGE")) return "judge";
  return null;
};

// ----------------------------------------------------------------- agents

export type Seat =
  | "prosecution"
  | "defense"
  | "judge"
  | "jury"
  | "analyst"
  | "auditor";

export const agentSeat = (agentId: string | undefined): Seat | null => {
  if (!agentId) return null;
  if (agentId.startsWith("prosecution")) return "prosecution";
  if (agentId.startsWith("defense")) return "defense";
  if (agentId.startsWith("judge")) return "judge";
  if (agentId.startsWith("jury")) return "jury";
  if (agentId.startsWith("evidence")) return "analyst";
  if (agentId.startsWith("auditor")) return "auditor";
  return null;
};

export const agentLabel = (agentId: string | undefined): string => {
  if (!agentId) return "Court";
  const juror = /^jury_(\d+)$/.exec(agentId);
  if (juror) return `Juror ${juror[1]}`;
  switch (agentSeat(agentId)) {
    case "prosecution":
      return "Prosecution";
    case "defense":
      return "Defense";
    case "judge":
      return "Judge";
    case "analyst":
      return "Evidence Analyst";
    case "auditor":
      return "Auditor";
    default:
      return titleCase(agentId);
  }
};

/** Tailwind classes per seat, so one colour follows an agent everywhere */
export const SEAT_STYLES: Record<
  Seat,
  { text: string; border: string; bg: string; dot: string }
> = {
  prosecution: {
    text: "text-rose-300",
    border: "border-rose-500/40",
    bg: "bg-rose-500/10",
    dot: "bg-rose-400",
  },
  defense: {
    text: "text-sky-300",
    border: "border-sky-500/40",
    bg: "bg-sky-500/10",
    dot: "bg-sky-400",
  },
  judge: {
    text: "text-amber-300",
    border: "border-amber-500/40",
    bg: "bg-amber-500/10",
    dot: "bg-amber-400",
  },
  jury: {
    text: "text-violet-300",
    border: "border-violet-500/40",
    bg: "bg-violet-500/10",
    dot: "bg-violet-400",
  },
  analyst: {
    text: "text-emerald-300",
    border: "border-emerald-500/40",
    bg: "bg-emerald-500/10",
    dot: "bg-emerald-400",
  },
  auditor: {
    text: "text-slate-300",
    border: "border-slate-500/40",
    bg: "bg-slate-500/10",
    dot: "bg-slate-400",
  },
};

export const seatStyle = (seat: Seat | null) =>
  seat ? SEAT_STYLES[seat] : SEAT_STYLES.auditor;

// ----------------------------------------------------------------- events

/** A one-line description of an event, for the live feed */
export function describeEvent(event: CourtEvent): string {
  const who = agentLabel(event.agent_id);
  switch (event.event_type) {
    case "CASE_LOADED":
      return `${event.case_id} loaded: ${event.facts} facts, ${event.evidence} evidence, ${event.witnesses} witnesses`;
    case "RULES_EVALUATED":
      return `The rule engine evaluated ${count(event.rules)} rule/subject pairs from ${event.bindings} bindings`;
    case "AGENT_STARTED":
      return `${who} is working...`;
    case "AGENT_ARGUMENT":
      return `${who} presented ${list(event.argument_ids)}`;
    case "AGENT_RESPONSE":
      return `${who} answered ${list(event.answered) || "the court"}`;
    case "EVIDENCE_ANALYZED":
      return `${who} analysed the record: ${claimSummary(event.claims)}, ${num(event.contradictions)} contradictions`;
    case "EVIDENCE_REVIEWED":
      return `${who} reviewed ${count(event.reviewed)} arguments, ${count(event.unsupported)} unsupported`;
    case "JUDGE_QUESTION":
      return `${who} asked ${count(event.questions)} question(s) about ${list(event.flagged)}`;
    case "JURY_DECISION":
      return `${who} (${String(event.round ?? "")}) voted: ${event.decision}`;
    case "JURY_VERDICT":
      return `Jury verdict (${event.rule}): ${verdicts(event.verdicts)}`;
    case "JUDGE_DECISION":
      return `${who} decided: ${event.decision}`;
    case "AUDIT_COMPLETED":
      return `${who} finished: ${event.overall_status}, ${num(event.findings)} findings`;
    case "STAGE_SKIPPED":
      return `Skipped: ${event.reason}`;
    case "CASE_COMPLETE":
      return "The case is complete";
    default:
      return event.event_type;
  }
}

const num = (value: unknown): number =>
  typeof value === "number" ? value : 0;

const count = (value: unknown): number =>
  Array.isArray(value)
    ? value.length
    : value && typeof value === "object"
      ? Object.keys(value).length
      : 0;

const list = (value: unknown): string =>
  Array.isArray(value) ? value.join(", ") : "";

const claimSummary = (value: unknown): string => {
  if (!value || typeof value !== "object") return "no claims";
  return Object.entries(value as Record<string, number>)
    .filter(([, n]) => n > 0)
    .map(([status, n]) => `${n} ${status}`)
    .join(", ");
};

const verdicts = (value: unknown): string => {
  if (!value || typeof value !== "object") return "";
  return Object.entries(value as Record<string, string>)
    .map(([charge, outcome]) => `${titleCase(charge)} ${outcome.replace("_", " ")}`)
    .join("; ");
};

/** Events worth a line in the feed: the "started" noise is shown as activity */
export const isFeedEvent = (event: CourtEvent): boolean =>
  event.event_type !== "AGENT_STARTED";

// ------------------------------------------------------------- formatting

export const titleCase = (value: string): string =>
  value
    .replace(/[_-]+/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());

export const percent = (value: number): string => `${Math.round(value * 100)}%`;

export const verdictLabel = (decision: string): string =>
  decision === "not_guilty" ? "Not guilty" : titleCase(decision);

export const clockTime = (iso: string): string => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
};

export const duration = (from: string | null, to: string | null): string => {
  if (!from) return "";
  const start = new Date(from).getTime();
  const end = to ? new Date(to).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end)) return "";
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
};

export const STATUS_STYLES: Record<RunStatus, string> = {
  queued: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  running: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  completed: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  failed: "bg-rose-500/15 text-rose-300 border-rose-500/40",
};

/** Spec section 24: this sentence has to be visible in the UI */
export const DISCLAIMER =
  "Research simulation only. This system does not provide legal advice or " +
  "determine real legal rights or obligations.";
