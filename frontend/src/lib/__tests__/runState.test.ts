/**
 * What the UI derives from the event stream alone.
 *
 * The fixture is a real run: the events and result of a full court procedure
 * produced by `run_court` with scripted agents (the backend's own
 * `tests/test_agents/test_court_graph.py` script), serialised exactly as the
 * API returns it.
 */

import { describe, expect, it } from "vitest";

import fixture from "@/lib/__fixtures__/trial-run.json";
import { deriveCourt, progress, timeline } from "@/lib/runState";
import { analysisOf, isTrialRun, judgmentOf } from "@/lib/result";
import type { CourtEvent, TrialRun } from "@/lib/types";

const run = fixture as unknown as TrialRun;
const events = run.event_history as CourtEvent[];

describe("deriveCourt, over a finished run", () => {
  const state = deriveCourt(events, "completed");

  it("ends at CASE_COMPLETE with nobody still working", () => {
    expect(state.currentStage).toBe("CASE_COMPLETE");
    expect(state.complete).toBe(true);
    expect(state.activeAgents).toEqual([]);
    expect(state.activeSeats).toEqual([]);
  });

  it("collects every argument the parties presented, in order", () => {
    const ids = state.argumentsPresented.map((a) => a.argumentId);
    expect(ids.slice(0, 4)).toEqual([
      "PR-OPEN-1",
      "PR-OPEN-2",
      "DF-OPEN-1",
      "DF-OPEN-2",
    ]);
    expect(ids).toContain("DF-CLOSE-2");
    expect(ids).toHaveLength(
      run.turns.reduce((n, turn) => n + turn.arguments.length, 0),
    );
  });

  it("remembers what the evidence review found unsupported", () => {
    expect(state.unsupported).toEqual(["PR-OPEN-2"]);
  });

  it("records the judge's questions and who they were put to", () => {
    expect(state.questionsAsked).toEqual([
      { questionId: "JQ1-1", addressedTo: "prosecution_agent" },
    ]);
  });

  it("records both jury rounds, the tally, and the judgment", () => {
    expect(state.votes.filter((v) => v.round === "independent")).toHaveLength(3);
    expect(state.votes.filter((v) => v.round === "deliberation")).toHaveLength(3);
    expect(state.juryVerdict).toEqual({
      burglary: "not_guilty",
      assault: "not_guilty",
    });
    expect(state.judgeDecision).toBe("burglary: not_guilty; assault: not_guilty");
    expect(state.auditStatus).toBe("minor_issues");
  });

  it("marks every stage of the procedure as done", () => {
    const states = timeline(state);
    expect(states.every((row) => row.state === "done")).toBe(true);
    expect(progress(state)).toBe(1);
  });
});

describe("deriveCourt, mid-trial", () => {
  const upToOpening = events.slice(
    0,
    events.findIndex((e) => e.event_type === "AGENT_ARGUMENT") + 1,
  );

  it("shows the stage running and the agent working", () => {
    const partway = deriveCourt(upToOpening.slice(0, -1), "running");
    expect(partway.activeAgents).toEqual(["prosecution_agent"]);
    expect(partway.activeSeats).toEqual(["prosecution"]);
    expect(partway.stageStates.PROSECUTION_OPENING).toBe("active");
  });

  it("clears the seat once that agent reports its argument", () => {
    const state = deriveCourt(upToOpening, "running");
    expect(state.activeAgents).toEqual([]);
    expect(state.stageStates.PROSECUTION_OPENING).toBe("done");
  });

  it("leaves stages that have not happened pending", () => {
    const state = deriveCourt(upToOpening, "running");
    const rows = Object.fromEntries(
      timeline(state).map((row) => [row.stage, row.state]),
    );
    expect(rows.JUDGE_DECISION).toBe("pending");
    expect(rows.CASE_COMPLETE).toBe("pending");
    expect(progress(state)).toBeGreaterThan(0);
    expect(progress(state)).toBeLessThan(1);
  });

  it("never leaves an agent working once the run has stopped", () => {
    const state = deriveCourt(upToOpening.slice(0, -1), "failed");
    expect(state.activeAgents).toEqual([]);
    expect(state.stageStates.PROSECUTION_OPENING).toBe("done");
  });

  it("handles a run with no events at all", () => {
    const state = deriveCourt([], "queued");
    expect(state.currentStage).toBeNull();
    expect(timeline(state).every((row) => row.state === "pending")).toBe(true);
    expect(progress(state)).toBe(0);
  });
});

describe("a skipped stage", () => {
  it("is shown as skipped, not as done", () => {
    const state = deriveCourt(
      [
        {
          stage: "CROSS_EXAMINATION",
          event_type: "STAGE_SKIPPED",
          timestamp: "2026-09-20T08:00:00Z",
          reason: "cross-examination is off",
        },
      ],
      "running",
    );
    expect(state.stageStates.CROSS_EXAMINATION).toBe("skipped");
    expect(progress(state)).toBeGreaterThan(0);
  });
});

describe("reading the result of each mode", () => {
  it("recognises a full trial", () => {
    expect(isTrialRun(run)).toBe(true);
    expect(judgmentOf(run)?.verdict.agent_id).toBe("judge_agent");
    expect(analysisOf(run)?.output.claims.length).toBeGreaterThan(0);
  });

  it("reads the judgment of a judge-only run", () => {
    const judgeOnly = {
      case: run.case,
      evaluation: run.evaluation,
      result: run.judgment,
      event_history: [],
    };
    expect(isTrialRun(judgeOnly)).toBe(false);
    expect(judgmentOf(judgeOnly)).toBe(run.judgment);
    expect(analysisOf(judgeOnly)).toBeNull();
  });

  it("reads the analysis of an evidence-only run", () => {
    const evidenceOnly = {
      case: run.case,
      evaluation: run.evaluation,
      analysis: run.evidence_analysis!,
      event_history: [],
    };
    expect(analysisOf(evidenceOnly)).toBe(run.evidence_analysis);
    expect(judgmentOf(evidenceOnly)).toBeNull();
  });

  it("has nothing to read before a run finishes", () => {
    expect(judgmentOf(null)).toBeNull();
    expect(analysisOf(null)).toBeNull();
    expect(isTrialRun(null)).toBe(false);
  });
});
