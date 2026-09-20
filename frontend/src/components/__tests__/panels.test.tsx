/**
 * The panels spec section 20 asks for, rendered from a real finished run.
 *
 * These assert what a person reads on the page: the arguments each side made,
 * the jury's votes, the judge's findings, and what the auditor found.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuditPanel } from "@/components/panels/AuditPanel";
import { DebatePanel } from "@/components/panels/DebatePanel";
import { EvidencePanel } from "@/components/panels/EvidencePanel";
import { JudgeDecisionPanel } from "@/components/panels/JudgeDecisionPanel";
import { JuryPanel } from "@/components/panels/JuryPanel";
import { RulesPanel, citationsByRule } from "@/components/panels/RulesPanel";
import fixture from "@/lib/__fixtures__/trial-run.json";
import type { RuleDetail, TrialRun } from "@/lib/types";

const run = fixture as unknown as TrialRun;

describe("Debate panel", () => {
  it("shows both sides, their arguments, and what they cite", () => {
    render(<DebatePanel run={run} />);
    expect(screen.getAllByText("Prosecution").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Defense").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/broken window/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("PR-OPEN-1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("E001").length).toBeGreaterThan(0);
  });

  it("marks the argument the evidence review found unsupported", () => {
    render(<DebatePanel run={run} />);
    expect(screen.getAllByText("Unsupported").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/not supported by what it cites/).length,
    ).toBeGreaterThan(0);
  });

  it("shows the judge's question where it was asked", () => {
    render(<DebatePanel run={run} />);
    expect(
      screen.getByText("The judge questions the parties"),
    ).toBeInTheDocument();
    expect(screen.getByText(/What in the record supports/)).toBeInTheDocument();
    expect(screen.getByText("to Prosecution")).toBeInTheDocument();
  });

  it("says so when nothing was argued", () => {
    render(<DebatePanel run={{ ...run, turns: [] }} />);
    expect(
      screen.getByText(/No arguments were presented/),
    ).toBeInTheDocument();
  });
});

describe("Evidence panel", () => {
  it("shows the analyst's claims with their status, and the record itself", () => {
    render(
      <EvidencePanel record={run.case} analysis={run.evidence_analysis} />,
    );
    expect(
      screen.getByText(/Alex entered the house without permission/),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Established").length).toBeGreaterThan(0);
    expect(screen.getByText("Evidence on the record")).toBeInTheDocument();
    expect(screen.getAllByText(/reliability/i).length).toBeGreaterThan(0);
  });

  it("still shows the record when the Evidence Agent did not run", () => {
    render(<EvidencePanel record={run.case} analysis={null} />);
    expect(
      screen.getByText(/The Evidence Agent did not run/),
    ).toBeInTheDocument();
    expect(screen.getByText("Evidence on the record")).toBeInTheDocument();
  });
});

describe("Jury panel", () => {
  it("shows the tally, the rule, and each juror's verdict", () => {
    render(
      <JuryPanel
        independent={run.jury_independent}
        deliberation={run.jury_deliberation}
        result={run.jury_result}
      />,
    );
    expect(screen.getByText(/Decision rule: Unanimous/)).toBeInTheDocument();
    expect(screen.getAllByText("Juror 1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not guilty").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Unanimous").length).toBeGreaterThan(0);
  });

  it("says so when no jury sat", () => {
    render(<JuryPanel independent={[]} deliberation={[]} result={null} />);
    expect(screen.getByText(/No jury sat/)).toBeInTheDocument();
  });
});

describe("Judge decision panel", () => {
  it("keeps findings, law, reasoning, and verdict apart", () => {
    render(
      <JudgeDecisionPanel
        judgment={run.judgment}
        agreement={run.judge_jury_agreement}
      />,
    );
    expect(screen.getByText("Verdict")).toBeInTheDocument();
    expect(screen.getByText("Findings of fact")).toBeInTheDocument();
    expect(screen.getByText("Applicable law")).toBeInTheDocument();
    expect(
      screen.getByText("Reasoning, element by element"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/Entry is proven; intent is not/).length,
    ).toBeGreaterThan(0);
  });

  it("shows whether the judge and the jury agreed", () => {
    render(
      <JudgeDecisionPanel
        judgment={run.judgment}
        agreement={run.judge_jury_agreement}
      />,
    );
    const section = screen.getByText("Judge and jury").parentElement!;
    // one row per charge, both decided the same way here
    expect(within(section).getAllByText(/Judge Not guilty/)).toHaveLength(2);
  });

  it("says so before the judge has decided", () => {
    render(<JudgeDecisionPanel judgment={null} />);
    expect(screen.getByText(/has not decided yet/)).toBeInTheDocument();
  });
});

describe("Audit panel", () => {
  it("shows the overall status and every category the spec asks for", () => {
    render(<AuditPanel audit={run.audit} />);
    expect(screen.getByText("Minor Issues")).toBeInTheDocument();
    for (const heading of [
      "Hallucinations",
      "Evidence violations",
      "Procedural violations",
      "Legal violations",
      "Reasoning issues",
    ]) {
      expect(
        screen.getByText(heading, { exact: false }),
      ).toBeInTheDocument();
    }
  });

  it("shows a finding with where it came from", () => {
    render(<AuditPanel audit={run.audit} />);
    expect(
      screen.getByText(/The Evidence Agent found PR-OPEN-2 unsupported/),
    ).toBeInTheDocument();
    expect(screen.getAllByText("check").length).toBeGreaterThan(0);
  });

  it("says so when there was no audit", () => {
    render(<AuditPanel audit={null} />);
    expect(screen.getByText(/was not audited/)).toBeInTheDocument();
  });
});

describe("Rules panel", () => {
  it("counts who cited each law", () => {
    const cited = citationsByRule(run);
    expect([...(cited.get("LAW_104") ?? [])]).toEqual(
      expect.arrayContaining(["Prosecution", "Judge"]),
    );
    expect(cited.has("LAW_999")).toBe(false);
  });

  it("separates the laws the agents used from the rest of the statute book", () => {
    const rules: RuleDetail[] = [
      {
        rule_id: "LAW_104",
        name: "Burglary",
        category: "offense",
        description: "Entering without authority to commit an offense",
        conditions: [
          { id: "C1", description: "Entry", required: true, depends_on_rule: null },
        ],
        effect: "burglary_offense_established",
        jurisdiction: "Republic of Arandia",
      },
      {
        rule_id: "LAW_301",
        name: "Attempt",
        category: "offense",
        description: "An attempt to commit an offense",
        conditions: [],
        effect: "attempt_established",
        jurisdiction: "Republic of Arandia",
      },
    ];
    render(
      <RulesPanel run={run} rules={rules} evaluation={run.evaluation} />,
    );
    expect(screen.getByText("Referenced by the agents")).toBeInTheDocument();
    expect(screen.getByText(/cited by/)).toBeInTheDocument();
    expect(
      screen.getByText(/The rest of the law of Arandia \(1\)/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("What the rule engine computed"),
    ).toBeInTheDocument();
  });
});
