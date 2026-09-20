/**
 * What the event stream says about a trial in progress.
 *
 * The finished panels read the run's `result`, which only exists once the run
 * ends. While it is still going, everything the UI shows is derived here from
 * the events alone.
 */

import { STAGES, agentSeat, type Seat } from "./court";
import type { CourtEvent, RunStatus } from "./types";

export type StageState = "pending" | "active" | "done" | "skipped";

export interface LiveArgument {
  argumentId: string;
  stage: string;
  agentId: string;
  timestamp: string;
}

export interface LiveVote {
  jurorId: string;
  round: string;
  decision: string;
  timestamp: string;
}

export interface LiveCourt {
  /** The last stage an event came from */
  currentStage: string | null;
  /** Agents that started work and have not reported finishing */
  activeAgents: string[];
  activeSeats: Seat[];
  stageStates: Record<string, StageState>;
  /** Argument IDs in the order they were presented */
  argumentsPresented: LiveArgument[];
  questionsAsked: { questionId: string; addressedTo: string }[];
  unsupported: string[];
  votes: LiveVote[];
  juryVerdict: Record<string, string> | null;
  judgeDecision: string | null;
  auditStatus: string | null;
  complete: boolean;
}

const EMPTY: LiveCourt = {
  currentStage: null,
  activeAgents: [],
  activeSeats: [],
  stageStates: {},
  argumentsPresented: [],
  questionsAsked: [],
  unsupported: [],
  votes: [],
  juryVerdict: null,
  judgeDecision: null,
  auditStatus: null,
  complete: false,
};

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];

export function deriveCourt(
  events: CourtEvent[],
  status: RunStatus = "running",
): LiveCourt {
  if (events.length === 0) {
    return { ...EMPTY, stageStates: {} };
  }

  const state: LiveCourt = {
    ...EMPTY,
    stageStates: {},
    activeAgents: [],
    activeSeats: [],
    argumentsPresented: [],
    questionsAsked: [],
    unsupported: [],
    votes: [],
  };
  const working = new Set<string>();

  for (const event of events) {
    state.currentStage = event.stage;

    if (event.event_type === "STAGE_SKIPPED") {
      state.stageStates[event.stage] = "skipped";
      continue;
    }
    state.stageStates[event.stage] = "done";

    switch (event.event_type) {
      case "AGENT_STARTED":
        if (event.agent_id) working.add(event.agent_id);
        state.stageStates[event.stage] = "active";
        break;

      case "AGENT_ARGUMENT":
      case "AGENT_RESPONSE":
        if (event.agent_id) working.delete(event.agent_id);
        for (const argumentId of strings(event.argument_ids)) {
          state.argumentsPresented.push({
            argumentId,
            stage: event.stage,
            agentId: event.agent_id ?? "",
            timestamp: event.timestamp,
          });
        }
        break;

      case "EVIDENCE_REVIEWED":
        if (event.agent_id) working.delete(event.agent_id);
        state.unsupported = [
          ...new Set([...state.unsupported, ...strings(event.unsupported)]),
        ];
        break;

      case "JUDGE_QUESTION":
        if (event.agent_id) working.delete(event.agent_id);
        for (const [questionId, addressedTo] of Object.entries(
          (event.questions as Record<string, string>) ?? {},
        )) {
          state.questionsAsked.push({ questionId, addressedTo });
        }
        break;

      case "JURY_DECISION":
        if (event.agent_id) working.delete(event.agent_id);
        state.votes.push({
          jurorId: event.agent_id ?? "",
          round: String(event.round ?? ""),
          decision: String(event.decision ?? ""),
          timestamp: event.timestamp,
        });
        break;

      case "JURY_VERDICT":
        state.juryVerdict = (event.verdicts as Record<string, string>) ?? null;
        break;

      case "JUDGE_DECISION":
        if (event.agent_id) working.delete(event.agent_id);
        state.judgeDecision = String(event.decision ?? "");
        break;

      case "AUDIT_COMPLETED":
        if (event.agent_id) working.delete(event.agent_id);
        state.auditStatus = String(event.overall_status ?? "");
        break;

      case "CASE_COMPLETE":
        state.complete = true;
        break;

      default:
        if (event.agent_id) working.delete(event.agent_id);
    }
  }

  // A run that has stopped has nobody working, whatever the last event said.
  if (status === "completed" || status === "failed") {
    working.clear();
    for (const [stage, value] of Object.entries(state.stageStates)) {
      if (value === "active") state.stageStates[stage] = "done";
    }
  }

  state.activeAgents = [...working];
  state.activeSeats = [
    ...new Set(
      state.activeAgents
        .map(agentSeat)
        .filter((seat): seat is Seat => seat !== null),
    ),
  ];
  return state;
}

/**
 * The procedure in order, each stage with the state the events give it.
 *
 * A stage the events have not mentioned is pending: the backend records a
 * skipped stage explicitly, so silence only ever means "not yet".
 */
export function timeline(
  state: LiveCourt,
): { stage: string; state: StageState }[] {
  return STAGES.map((stage) => ({
    stage,
    state: state.stageStates[stage] ?? ("pending" as StageState),
  }));
}

/** Which of the spec's headline stages the case has reached, 0 to 1 */
export function progress(state: LiveCourt): number {
  const done = STAGES.filter((stage) =>
    ["done", "skipped"].includes(state.stageStates[stage] ?? ""),
  ).length;
  return done / STAGES.length;
}
