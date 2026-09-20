/**
 * The courtroom vocabulary: who an agent is, what a stage is called, and what
 * one line of the live feed says about an event.
 */

import { describe, expect, it } from "vitest";

import {
  DISCLAIMER,
  agentLabel,
  agentSeat,
  describeEvent,
  duration,
  percent,
  stageLabel,
  stageSide,
  titleCase,
  verdictLabel,
} from "@/lib/court";
import type { CourtEvent } from "@/lib/types";

const event = (partial: Partial<CourtEvent>): CourtEvent => ({
  stage: "PROSECUTION_OPENING",
  event_type: "AGENT_ARGUMENT",
  timestamp: "2026-09-20T08:13:14.321645Z",
  ...partial,
});

describe("agents", () => {
  it("names each seat from its agent id", () => {
    expect(agentLabel("prosecution_agent")).toBe("Prosecution");
    expect(agentLabel("defense_agent")).toBe("Defense");
    expect(agentLabel("judge_agent")).toBe("Judge");
    expect(agentLabel("evidence_agent")).toBe("Evidence Analyst");
    expect(agentLabel("auditor_agent")).toBe("Auditor");
    expect(agentLabel("jury_2")).toBe("Juror 2");
  });

  it("falls back to the court when no agent is named", () => {
    expect(agentLabel(undefined)).toBe("Court");
    expect(agentSeat(undefined)).toBeNull();
  });

  it("maps a stage to the seat that speaks at it", () => {
    expect(stageSide("PROSECUTION_REBUTTAL")).toBe("prosecution");
    expect(stageSide("DEFENSE_OPENING")).toBe("defense");
    expect(stageSide("JUDGE_QUESTIONS")).toBe("judge");
    expect(stageSide("JURY_DELIBERATION")).toBe("jury");
    expect(stageSide("EVIDENCE_ANALYSIS")).toBe("analyst");
    expect(stageSide("LEGAL_PROCESS_AUDIT")).toBe("auditor");
    expect(stageSide("CASE_COMPLETE")).toBeNull();
  });
});

describe("describeEvent", () => {
  it("reports an argument with its IDs", () => {
    expect(
      describeEvent(
        event({
          agent_id: "prosecution_agent",
          argument_ids: ["PR-OPEN-1", "PR-OPEN-2"],
        }),
      ),
    ).toBe("Prosecution presented PR-OPEN-1, PR-OPEN-2");
  });

  it("reports an answer to the judge", () => {
    expect(
      describeEvent(
        event({
          stage: "JUDGE_QUESTIONS",
          event_type: "AGENT_RESPONSE",
          agent_id: "prosecution_agent",
          answered: ["JQ1-1"],
        }),
      ),
    ).toBe("Prosecution answered JQ1-1");
  });

  it("summarises the evidence analysis by claim status", () => {
    expect(
      describeEvent(
        event({
          stage: "EVIDENCE_ANALYSIS",
          event_type: "EVIDENCE_ANALYZED",
          agent_id: "evidence_agent",
          claims: { established: 2, disputed: 1, unsupported: 0 },
          contradictions: 3,
        }),
      ),
    ).toBe(
      "Evidence Analyst analysed the record: 2 established, 1 disputed, 3 contradictions",
    );
  });

  it("reports what the review found unsupported", () => {
    expect(
      describeEvent(
        event({
          stage: "EVIDENCE_REVIEW",
          event_type: "EVIDENCE_REVIEWED",
          agent_id: "evidence_agent",
          reviewed: ["PR-OPEN-1", "PR-OPEN-2"],
          unsupported: ["PR-OPEN-2"],
        }),
      ),
    ).toBe("Evidence Analyst reviewed 2 arguments, 1 unsupported");
  });

  it("reports the judge's questions", () => {
    expect(
      describeEvent(
        event({
          stage: "JUDGE_QUESTIONS",
          event_type: "JUDGE_QUESTION",
          agent_id: "judge_agent",
          flagged: ["PR-OPEN-2"],
          questions: { "JQ1-1": "prosecution_agent" },
        }),
      ),
    ).toBe("Judge asked 1 question(s) about PR-OPEN-2");
  });

  it("reports a juror's vote and the jury's tally", () => {
    expect(
      describeEvent(
        event({
          stage: "JURY_INDEPENDENT_DELIBERATION",
          event_type: "JURY_DECISION",
          agent_id: "jury_1",
          round: "independent",
          decision: "burglary: not_guilty",
        }),
      ),
    ).toBe("Juror 1 (independent) voted: burglary: not_guilty");

    expect(
      describeEvent(
        event({
          stage: "JURY_DELIBERATION",
          event_type: "JURY_VERDICT",
          rule: "unanimous",
          verdicts: { burglary: "not_guilty", assault: "guilty" },
        }),
      ),
    ).toBe("Jury verdict (unanimous): Burglary not guilty; Assault guilty");
  });

  it("reports the audit and a skipped stage", () => {
    expect(
      describeEvent(
        event({
          stage: "LEGAL_PROCESS_AUDIT",
          event_type: "AUDIT_COMPLETED",
          agent_id: "auditor_agent",
          overall_status: "minor_issues",
          findings: 1,
        }),
      ),
    ).toBe("Auditor finished: minor_issues, 1 findings");

    expect(
      describeEvent(
        event({
          stage: "CROSS_EXAMINATION",
          event_type: "STAGE_SKIPPED",
          reason: "cross-examination is off",
        }),
      ),
    ).toBe("Skipped: cross-examination is off");
  });

  it("falls back to the event type it does not know", () => {
    expect(describeEvent(event({ event_type: "SOMETHING_NEW" }))).toBe(
      "SOMETHING_NEW",
    );
  });
});

describe("formatting", () => {
  it("labels stages and verdicts for people", () => {
    expect(stageLabel("JURY_INDEPENDENT_DELIBERATION")).toBe(
      "Jury deliberates independently",
    );
    expect(stageLabel("UNKNOWN_STAGE")).toBe("Unknown Stage");
    expect(verdictLabel("not_guilty")).toBe("Not guilty");
    expect(titleCase("aggravated_assault")).toBe("Aggravated Assault");
    expect(percent(0.856)).toBe("86%");
  });

  it("measures how long a run took", () => {
    expect(
      duration("2026-09-20T08:00:00Z", "2026-09-20T08:00:42Z"),
    ).toBe("42s");
    expect(
      duration("2026-09-20T08:00:00Z", "2026-09-20T08:03:07Z"),
    ).toBe("3m 7s");
    expect(duration(null, null)).toBe("");
  });

  it("carries the disclaimer spec section 24 requires", () => {
    expect(DISCLAIMER).toContain("Research simulation only");
    expect(DISCLAIMER).toContain("does not provide legal advice");
  });
});
