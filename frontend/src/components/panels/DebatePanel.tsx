/**
 * Debate panel: what each side argued, in the order the court heard it.
 *
 * The judge's questions and the answers to them sit in the same sequence,
 * because that is where they happened. An argument the Evidence Agent found
 * unsupported is marked as such - that finding is the reason the judge asks.
 */

import { agentLabel, percent, seatStyle, stageLabel, titleCase } from "@/lib/court";
import type {
  AdvocateTurn,
  Argument,
  ArgumentReview,
  JudgeQuestionRound,
  TrialRun,
} from "@/lib/types";
import { Badge, Empty, IdList, Meter, cx } from "@/components/ui";

export function DebatePanel({ run }: { run: TrialRun }) {
  const reviews = new Map<string, ArgumentReview>();
  for (const review of run.evidence_reviews) {
    for (const entry of review.output.reviews) {
      reviews.set(entry.argument_id, entry);
    }
  }

  if (run.turns.length === 0) {
    return <Empty>No arguments were presented in this run.</Empty>;
  }

  // The judge's questions belong above the answers to them. A round can put
  // questions to both parties, so the round is read from the question IDs the
  // answer cites (JQ2-1 is the first question of round two) rather than
  // counted - and the header is shown once, above the first answer to it.
  const rounds = new Map<number, JudgeQuestionRound>();
  for (const round of run.judge_question_rounds) rounds.set(round.round, round);
  const introduced = new Set<number>();

  return (
    <div className="space-y-4">
      {run.turns.map((turn, index) => {
        const round =
          turn.stage === "JUDGE_QUESTIONS"
            ? rounds.get(roundAnswered(turn) ?? 0)
            : undefined;
        const first = round && !introduced.has(round.round);
        if (round) introduced.add(round.round);
        return (
          <div key={`${turn.stage}-${turn.agent_id}-${index}`}>
            {first && <QuestionRound round={round} />}
            <TurnCard turn={turn} reviews={reviews} />
          </div>
        );
      })}
    </div>
  );
}

/** Which round of questions a turn is answering, from the IDs it cites */
function roundAnswered(turn: AdvocateTurn): number | null {
  for (const argument of turn.arguments) {
    for (const id of argument.counter_argument_ids) {
      const match = /^JQ(\d+)-/.exec(id);
      if (match) return Number(match[1]);
    }
  }
  return null;
}

function TurnCard({
  turn,
  reviews,
}: {
  turn: AdvocateTurn;
  reviews: Map<string, ArgumentReview>;
}) {
  const style = seatStyle(turn.role === "prosecution" ? "prosecution" : "defense");
  return (
    <article
      className={cx(
        "rounded-xl border bg-slate-900/40 p-4",
        style.border,
        turn.role === "defense" && "lg:ms-10",
        turn.role === "prosecution" && "lg:me-10",
      )}
    >
      <header className="flex flex-wrap items-center gap-2">
        <span className={cx("size-2 rounded-full", style.dot)} />
        <span className={cx("text-sm font-medium", style.text)}>
          {agentLabel(turn.agent_id)}
        </span>
        <Badge>{stageLabel(turn.stage)}</Badge>
        {turn.flags.length > 0 && (
          <Badge
            className="border-amber-500/40 bg-amber-500/10 text-amber-300"
            title={turn.flags.join("; ")}
          >
            {turn.flags.length} flag(s)
          </Badge>
        )}
      </header>

      <p className="mt-2 text-sm text-slate-300 italic">{turn.statement}</p>

      <ul className="mt-3 space-y-2">
        {turn.arguments.map((argument) => (
          <ArgumentCard
            key={argument.argument_id}
            argument={argument}
            review={reviews.get(argument.argument_id)}
          />
        ))}
      </ul>
    </article>
  );
}

const SUPPORT_STYLES: Record<string, string> = {
  supported: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  partially_supported: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  unsupported: "border-rose-500/40 bg-rose-500/10 text-rose-300",
};

export function ArgumentCard({
  argument,
  review,
}: {
  argument: Argument;
  review?: ArgumentReview;
}) {
  return (
    <li className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] text-slate-500">
          {argument.argument_id}
        </span>
        {review && (
          <Badge
            className={SUPPORT_STYLES[review.support]}
            title={review.issues.join("; ") || review.reasoning}
          >
            {titleCase(review.support)}
          </Badge>
        )}
        <span className="ms-auto flex items-center gap-1.5 text-xs text-slate-500">
          confidence
          <Meter
            value={argument.confidence}
            tone={argument.confidence >= 0.7 ? "emerald" : "amber"}
          />
          {percent(argument.confidence)}
        </span>
      </div>

      <p className="mt-1.5 text-sm text-slate-100">{argument.claim}</p>
      <p className="mt-1 text-sm text-slate-400">{argument.reasoning}</p>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <IdList label="evidence" ids={argument.evidence_ids} />
        <IdList label="facts" ids={argument.fact_ids} />
        <IdList label="witnesses" ids={argument.witness_ids} />
        <IdList label="law" ids={argument.law_ids} />
        <IdList label="answers" ids={argument.counter_argument_ids} />
      </div>

      {review && review.issues.length > 0 && (
        <ul className="mt-2 border-t border-slate-800 pt-2 text-xs text-rose-300">
          {review.issues.map((issue) => (
            <li key={issue}>· {issue}</li>
          ))}
        </ul>
      )}
    </li>
  );
}

function QuestionRound({ round }: { round: JudgeQuestionRound }) {
  const style = seatStyle("judge");
  return (
    <article
      className={cx(
        "mb-3 rounded-xl border bg-amber-500/5 p-4",
        style.border,
        "lg:mx-16",
      )}
    >
      <header className="flex flex-wrap items-center gap-2">
        <span aria-hidden>⚖️</span>
        <span className={cx("text-sm font-medium", style.text)}>
          The judge questions the parties
        </span>
        <Badge>Round {round.round}</Badge>
        <IdList label="about" ids={round.flagged_argument_ids} />
      </header>
      <ul className="mt-2 space-y-2">
        {round.questions.map((question) => (
          <li
            key={question.question_id}
            className="rounded-lg border border-slate-800 bg-slate-950/40 p-3"
          >
            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              <span className="font-mono text-slate-500">
                {question.question_id}
              </span>
              <Badge>to {agentLabel(question.addressed_to)}</Badge>
              <IdList ids={question.argument_ids} />
            </div>
            <p className="mt-1.5 text-sm text-slate-100">{question.question}</p>
            <p className="mt-1 text-xs text-slate-500">{question.reason}</p>
          </li>
        ))}
      </ul>
    </article>
  );
}
