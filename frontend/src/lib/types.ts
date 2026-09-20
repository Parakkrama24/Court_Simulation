/**
 * The API contract, in TypeScript.
 *
 * These mirror `backend/app/api/schemas.py` and the domain models it
 * serialises. Anything the backend types loosely as a dict is typed here as
 * precisely as the backend actually produces it, so the panels can render it
 * without casts.
 */

// ---------------------------------------------------------------- the case

export type FactStatus = "established" | "disputed" | "unknown";

export type EvidenceType =
  | "physical"
  | "testimonial"
  | "documentary"
  | "digital"
  | "forensic"
  | "circumstantial";

export interface Fact {
  fact_id: string;
  description: string;
  source: string;
  status: FactStatus;
  metadata: Record<string, unknown>;
}

export interface Evidence {
  evidence_id: string;
  type: EvidenceType;
  description: string;
  source: string;
  supports: string[];
  contradicts: string[];
  reliability: number;
  metadata: Record<string, unknown>;
}

export interface Witness {
  witness_id: string;
  name: string;
  statement: string;
  reliability_factors: Record<string, unknown>;
  related_evidence: string[];
  metadata: Record<string, unknown>;
}

export interface Case {
  case_id: string;
  title: string;
  description: string;
  jurisdiction: string;
  case_type: "criminal" | "civil";
  defendant: string;
  prosecution: string;
  facts: Fact[];
  evidence: Evidence[];
  witnesses: Witness[];
  charges: string[];
  applicable_laws: string[];
  status: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export interface CaseSummary {
  case_id: string;
  title: string;
  defendant: string;
  charges: string[];
  case_type: string;
  jurisdiction: string;
  facts: number;
  evidence: number;
  witnesses: number;
  applicable_laws: string[];
  runnable: boolean;
}

// -------------------------------------------------------- the legal rules

export type LegalCategory =
  | "offense"
  | "defense"
  | "principle"
  | "evidence_rule"
  | "procedure";

export interface RuleCondition {
  id: string;
  description: string;
  required: boolean;
  depends_on_rule: string | null;
}

export interface RuleDetail {
  rule_id: string;
  name: string;
  category: LegalCategory;
  description: string;
  conditions: RuleCondition[];
  effect: string;
  jurisdiction: string;
}

// --------------------------------------------- what the rule engine decided

export type ConditionStatus =
  | "satisfied"
  | "unsatisfied"
  | "contested"
  | "indeterminate";

export type RuleStatus =
  | "satisfied"
  | "not_satisfied"
  | "indeterminate"
  | "not_applicable";

export interface ConditionEvaluation {
  rule_id: string;
  condition_id: string;
  description: string;
  required: boolean;
  status: ConditionStatus;
  support_strength: number;
  contradiction_strength: number;
  supporting_fact_ids: string[];
  supporting_evidence_ids: string[];
  contradicting_fact_ids: string[];
  contradicting_evidence_ids: string[];
  weights: {
    reference_id: string;
    reference_type: string;
    weight: number;
    explanation: string;
  }[];
  reasoning: string;
}

export interface RuleEvaluation {
  rule_id: string;
  rule_name: string;
  category: LegalCategory;
  subject: string;
  status: RuleStatus;
  effect: string;
  effect_applies: boolean;
  conditions: ConditionEvaluation[];
  reasoning: string;
}

export interface WitnessAssessment {
  witness_id: string;
  name: string;
  reliability_score: number;
  positive_factors: string[];
  challenge_grounds: string[];
  unscored_factors: string[];
  reasoning: string;
}

export interface CaseEvaluation {
  case_id: string;
  rule_evaluations: RuleEvaluation[];
  witness_assessments: WitnessAssessment[];
  unevaluated_rules: string[];
  conflicting_evidence: {
    type: string;
    rule_id: string;
    condition_id: string;
    subject: string;
    supporting_evidence: string[];
    contradicting_evidence: string[];
    description: string;
  }[];
  policy: Record<string, unknown>;
}

export interface EvidenceProvenance {
  evidence_id: string;
  evidence_type: string;
  source: string;
  handled_by: string | null;
  date: string | null;
  witness_id: string | null;
  supports_facts: string[];
  contradicts_facts: string[];
  recorded_reliability: number;
  gaps: string[];
}

export interface CaseDetail {
  case: Case;
  rule_evaluation: CaseEvaluation;
  evidence_provenance: EvidenceProvenance[];
  bindings: number;
  runnable: boolean;
}

// ------------------------------------------------------------ the trial

export interface Argument {
  argument_id: string;
  agent_id: string;
  claim: string;
  evidence_ids: string[];
  fact_ids: string[];
  witness_ids: string[];
  law_ids: string[];
  counter_argument_ids: string[];
  reasoning: string;
  confidence: number;
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface CourtMessage {
  message_id: string;
  case_id: string;
  sender: string;
  recipient: string;
  message_type: string;
  stage: string;
  claim: string;
  argument_ids: string[];
  evidence_ids: string[];
  law_ids: string[];
  reasoning: string;
  timestamp?: string;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  calls?: number;
}

export interface AdvocateTurn {
  stage: string;
  role: "prosecution" | "defense";
  agent_id: string;
  statement: string;
  arguments: Argument[];
  message: CourtMessage;
  flags: string[];
  usage: TokenUsage;
}

export type ClaimStatus = "established" | "disputed" | "unsupported";

export interface AnalysedClaim {
  claim: string;
  fact_ids: string[];
  supporting_evidence_ids: string[];
  supporting_witness_ids: string[];
  contradicting_evidence_ids: string[];
  contradicting_witness_ids: string[];
  status: ClaimStatus;
  confidence: number;
  reasoning: string;
}

export interface EvidenceAssessment {
  evidence_id: string;
  directness: "direct" | "circumstantial";
  fact_ids: string[];
  reliability_concerns: string[];
  reasoning: string;
}

export interface Contradiction {
  description: string;
  evidence_ids: string[];
  witness_ids: string[];
  fact_ids: string[];
  significance: string;
}

export interface MissingEvidence {
  description: string;
  elements: { rule_id: string; condition_id: string }[];
  why_it_matters: string;
}

/** A witness's reliability under evidence rule E003, as the analyst read it */
export interface AnalysedWitness {
  witness_id: string;
  rating: "high" | "moderate" | "low";
  grounds: string[];
  reasoning: string;
}

export interface EvidenceAnalysis {
  output: {
    claims: AnalysedClaim[];
    evidence: EvidenceAssessment[];
    contradictions: Contradiction[];
    witnesses: AnalysedWitness[];
    missing_evidence: MissingEvidence[];
    summary: string;
  };
  provenance: EvidenceProvenance[];
  message: CourtMessage;
  flags: string[];
  usage: TokenUsage;
}

export interface ArgumentReview {
  argument_id: string;
  support: "supported" | "partially_supported" | "unsupported";
  issues: string[];
  reasoning: string;
}

export interface EvidenceReview {
  output: { reviews: ArgumentReview[] };
  message: CourtMessage;
  flags: string[];
  usage: TokenUsage;
}

export interface JudgeQuestion {
  question_id: string;
  case_id: string;
  addressed_to: string;
  argument_ids: string[];
  question: string;
  reason: string;
  round: number;
  timestamp: string;
}

export interface JudgeQuestionRound {
  round: number;
  flagged_argument_ids: string[];
  questions: JudgeQuestion[];
  message: CourtMessage;
  usage: TokenUsage;
}

export interface Verdict {
  verdict_id: string;
  case_id: string;
  agent_id: string;
  charges: string[];
  decision: string;
  reasoning: string;
  evidence_used: string[];
  laws_used: string[];
  unresolved_questions: string[];
  confidence: number;
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface ChargeVerdict {
  charge: string;
  verdict: "guilty" | "not_guilty";
  fact_ids: string[];
  evidence_ids: string[];
  witness_ids: string[];
  rule_ids: string[];
  reasoning: string;
  confidence: number;
}

export interface JurorDecision {
  juror_id: string;
  stage: string;
  output: {
    charge_verdicts: ChargeVerdict[];
    arguments_considered: string[];
    uncertainties: string[];
    reasoning: string;
    confidence: number;
  };
  verdict: Verdict;
  message: CourtMessage;
  changed_charges: string[];
  usage: TokenUsage;
}

export interface ChargeTally {
  charge: string;
  guilty: string[];
  not_guilty: string[];
  outcome: "guilty" | "not_guilty" | "hung";
  unanimous: boolean;
  agreement: number;
}

export interface JuryResult {
  rule: string;
  jurors: string[];
  independent: ChargeTally[];
  final: ChargeTally[];
  vote_changes: {
    juror_id: string;
    charge: string;
    from: string;
    to: string;
  }[];
  deliberated: boolean;
}

export interface ElementFinding {
  condition_id: string;
  assessment: string;
  fact_ids: string[];
  evidence_ids: string[];
  reasoning: string;
}

export interface ChargeDecision {
  charge: string;
  rule_id: string;
  elements: ElementFinding[];
  defenses_considered: {
    rule_id: string;
    assessment: string;
    reasoning: string;
  }[];
  decision: "guilty" | "not_guilty";
  reasoning: string;
  confidence: number;
}

export interface JudgeResult {
  verdict: Verdict;
  decision: {
    established_facts: {
      fact_id: string;
      finding: string;
      evidence_ids: string[];
    }[];
    disputed_facts: {
      fact_id: string;
      issue: string;
      supporting_evidence_ids: string[];
      contradicting_evidence_ids: string[];
      resolution: string;
    }[];
    applicable_rules: { rule_id: string; relevance: string }[];
    arguments_considered: string[];
    analysis: string;
    charge_decisions: ChargeDecision[];
  };
  divergences: Record<string, unknown>[];
  usage: TokenUsage;
}

export type FindingSeverity = "info" | "minor" | "major" | "critical";

export type FindingCategory =
  | "evidence"
  | "legal"
  | "procedural"
  | "reasoning"
  | "hallucination";

export interface AuditFinding {
  finding_id: string;
  category: FindingCategory;
  severity: FindingSeverity;
  check: string;
  agent_id: string | null;
  stage: string | null;
  description: string;
  references: string[];
  source: "deterministic" | "auditor_agent";
}

export interface AuditReport {
  audit_id: string;
  case_id: string;
  evidence_violations: Record<string, unknown>[];
  legal_violations: Record<string, unknown>[];
  procedural_violations: Record<string, unknown>[];
  reasoning_issues: Record<string, unknown>[];
  hallucinations: Record<string, unknown>[];
  final_assessment: string;
  timestamp: string;
  metadata: {
    overall_status: string;
    severity_counts: Record<FindingSeverity, number>;
    sources: { deterministic: number; auditor_agent: number };
    deterministic_only: boolean;
    decision_chain: { link: string; rating: string; note: string }[];
    auditor_model?: string;
  };
}

export interface ProcessAudit {
  findings: AuditFinding[];
  report: AuditReport;
  auditor: Record<string, unknown> | null;
}

/** The full `court` run: everything one trial produced */
export interface TrialRun {
  case: Case;
  evaluation: CaseEvaluation;
  evidence_analysis: EvidenceAnalysis | null;
  evidence_reviews: EvidenceReview[];
  turns: AdvocateTurn[];
  judge_question_rounds: JudgeQuestionRound[];
  jury_independent: JurorDecision[];
  jury_deliberation: JurorDecision[];
  jury_result: JuryResult | null;
  judge_jury_agreement: {
    charge: string;
    judge: string;
    jury: string;
    agrees: boolean;
  }[];
  messages: CourtMessage[];
  judgment: JudgeResult;
  audit: ProcessAudit | null;
  event_history: CourtEvent[];
}

/** `judge` mode: the case straight to the judge, one call */
export interface JudgeOnlyRun {
  case: Case;
  evaluation: CaseEvaluation;
  result: JudgeResult;
  event_history: CourtEvent[];
}

/** `evidence` mode: the Evidence Agent's analysis alone */
export interface EvidenceRun {
  case: Case;
  evaluation: CaseEvaluation;
  analysis: EvidenceAnalysis;
  event_history: CourtEvent[];
}

export type RunResult = TrialRun | JudgeOnlyRun | EvidenceRun;

// ------------------------------------------------------------- the run

export type RunMode = "court" | "judge" | "evidence";
export type RunStatus = "queued" | "running" | "completed" | "failed";

export interface SimulationRequest {
  mode: RunMode;
  provider?: string | null;
  model?: string | null;
  evidence: boolean;
  cross_examination: boolean;
  judge_questions: boolean;
  question_rounds: number;
  jury: boolean;
  jurors: number;
  deliberation: boolean;
  jury_rule: "unanimous" | "majority";
  audit: boolean;
  audit_agent: boolean;
  max_attempts: number;
  strict_engine_alignment: boolean;
}

export interface RunSummary {
  run_id: string;
  case_id: string;
  mode: RunMode;
  status: RunStatus;
  current_stage: string;
  event_count: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface RunDetail extends RunSummary {
  options: SimulationRequest;
  result: RunResult | null;
  usage: TokenUsage;
}

export interface EventPage {
  run_id: string;
  status: RunStatus;
  events: CourtEvent[];
  next_index: number;
}

export interface HealthResponse {
  status: string;
  phase: string;
  cases: number;
  rules: number;
  active_runs: number;
  provider: string | null;
}

// --------------------------------------------------------- the event feed

/** Spec section 21 event types, plus the ones the workflow adds */
export type CourtEventType =
  | "CASE_LOADED"
  | "RULES_EVALUATED"
  | "AGENT_STARTED"
  | "AGENT_ARGUMENT"
  | "AGENT_RESPONSE"
  | "EVIDENCE_ANALYZED"
  | "EVIDENCE_REVIEWED"
  | "JUDGE_QUESTION"
  | "JURY_DECISION"
  | "JURY_VERDICT"
  | "JUDGE_DECISION"
  | "AUDIT_COMPLETED"
  | "STAGE_SKIPPED"
  | "CASE_COMPLETE";

/**
 * One entry of a run's event history.
 *
 * `stage`, `event_type`, and `timestamp` are always there; the rest depends on
 * the event, which is why details are read through helpers rather than a union
 * of two dozen shapes.
 */
export interface CourtEvent {
  stage: string;
  event_type: CourtEventType | string;
  timestamp: string;
  agent_id?: string;
  reason?: string;
  [key: string]: unknown;
}
