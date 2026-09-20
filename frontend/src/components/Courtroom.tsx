/**
 * The courtroom itself: prosecution, judge, and defense across the bench,
 * with the jury, the evidence analyst, and the auditor below.
 *
 * A seat lights up while that agent is working - the events say who started
 * and who finished, so this is the simulation's own state, not an animation.
 */

import { SEAT_STYLES, agentLabel, stageLabel, type Seat } from "@/lib/court";
import type { LiveCourt } from "@/lib/runState";
import { Badge, cx } from "@/components/ui";

const SEATS: { seat: Seat; icon: string; title: string; role: string }[] = [
  {
    seat: "prosecution",
    icon: "🧑‍⚖️",
    title: "Prosecution",
    role: "Argues the charges",
  },
  { seat: "judge", icon: "⚖️", title: "Judge", role: "Decides the case" },
  {
    seat: "defense",
    icon: "🧑‍⚖️",
    title: "Defense",
    role: "Answers the charges",
  },
];

const GALLERY: { seat: Seat; icon: string; title: string; role: string }[] = [
  {
    seat: "analyst",
    icon: "🔬",
    title: "Evidence Analyst",
    role: "Neutral: what the record supports",
  },
  { seat: "jury", icon: "👥", title: "Jury", role: "Decides independently" },
  {
    seat: "auditor",
    icon: "📋",
    title: "Auditor",
    role: "Checks the process afterwards",
  },
];

export function Courtroom({
  state,
  caseTitle,
  jurors,
}: {
  state: LiveCourt;
  caseTitle: string;
  jurors: number;
}) {
  const active = new Set(state.activeSeats);

  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/40">
      <header className="border-b border-slate-700/50 px-4 py-2 text-center">
        <p className="font-[family-name:var(--font-display)] text-sm tracking-[0.2em] text-slate-300 uppercase">
          Case: {caseTitle}
        </p>
        {state.currentStage && (
          <p className="text-xs text-amber-300/80">
            {stageLabel(state.currentStage)}
          </p>
        )}
      </header>

      <div className="grid gap-3 p-4 sm:grid-cols-3">
        {SEATS.map((seat) => (
          <SeatCard
            key={seat.seat}
            {...seat}
            active={active.has(seat.seat)}
            detail={
              seat.seat === "judge"
                ? state.judgeDecision
                  ? `Decided: ${state.judgeDecision}`
                  : state.questionsAsked.length > 0
                    ? `${state.questionsAsked.length} question(s) put to the parties`
                    : null
                : `${state.argumentsPresented.filter((a) => a.agentId.startsWith(seat.seat)).length} arguments`
            }
          />
        ))}
      </div>

      <div className="grid gap-3 border-t border-slate-800 p-4 sm:grid-cols-3">
        {GALLERY.map((seat) => (
          <SeatCard
            key={seat.seat}
            {...seat}
            small
            active={active.has(seat.seat)}
            detail={
              seat.seat === "jury"
                ? state.votes.length > 0
                  ? `${state.votes.length} of ${jurors * 2} votes cast`
                  : `${jurors} jurors`
                : seat.seat === "auditor"
                  ? state.auditStatus
                    ? `Audit: ${state.auditStatus.replace("_", " ")}`
                    : null
                  : state.unsupported.length > 0
                    ? `${state.unsupported.length} argument(s) unsupported`
                    : null
            }
          />
        ))}
      </div>

      {state.activeAgents.length > 0 && (
        <p className="border-t border-slate-800 px-4 py-2 text-xs text-amber-200/80">
          Now speaking: {state.activeAgents.map(agentLabel).join(", ")}
        </p>
      )}
    </div>
  );
}

function SeatCard({
  seat,
  icon,
  title,
  role,
  active,
  detail,
  small,
}: {
  seat: Seat;
  icon: string;
  title: string;
  role: string;
  active: boolean;
  detail?: string | null;
  small?: boolean;
}) {
  const style = SEAT_STYLES[seat];
  return (
    <div
      className={cx(
        "rounded-lg border p-3 text-center transition-colors",
        active
          ? cx(style.border, style.bg, "speaking")
          : "border-slate-800 bg-slate-950/40",
      )}
    >
      <div className={cx(small ? "text-xl" : "text-3xl")} aria-hidden>
        {icon}
      </div>
      <p
        className={cx(
          "mt-1 font-[family-name:var(--font-display)]",
          small ? "text-sm" : "text-base",
          active ? style.text : "text-slate-300",
        )}
      >
        {title}
      </p>
      {!small && <p className="text-[11px] text-slate-500">{role}</p>}
      {detail && (
        <Badge className={cx("mt-2", style.border, style.bg, style.text)}>
          {detail}
        </Badge>
      )}
      {active && (
        <p className="mt-1 text-[11px] text-amber-200/80">working…</p>
      )}
    </div>
  );
}
