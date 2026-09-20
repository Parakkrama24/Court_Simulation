/**
 * Reading a finished run.
 *
 * The three modes return three different shapes - a full `TrialRun`, a
 * `JudgeOnlyRun`, or an `EvidenceRun` - so the panels ask these helpers for
 * the part they need instead of guessing.
 */

import type {
  EvidenceAnalysis,
  EvidenceRun,
  JudgeOnlyRun,
  JudgeResult,
  RunResult,
  TrialRun,
} from "./types";

export const isTrialRun = (result: RunResult | null): result is TrialRun =>
  !!result && "judgment" in result;

export const isJudgeOnlyRun = (
  result: RunResult | null,
): result is JudgeOnlyRun => !!result && "result" in result;

export const isEvidenceRun = (
  result: RunResult | null,
): result is EvidenceRun => !!result && "analysis" in result;

export const judgmentOf = (result: RunResult | null): JudgeResult | null => {
  if (isTrialRun(result)) return result.judgment;
  if (isJudgeOnlyRun(result)) return result.result;
  return null;
};

export const analysisOf = (
  result: RunResult | null,
): EvidenceAnalysis | null => {
  if (isTrialRun(result)) return result.evidence_analysis;
  if (isEvidenceRun(result)) return result.analysis;
  return null;
};
