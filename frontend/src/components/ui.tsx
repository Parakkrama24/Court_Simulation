/**
 * The small pieces every panel is built from.
 *
 * Deliberately plain: a card, a badge, a chip for a record ID, a meter for a
 * score. The panels carry the meaning; these only make it legible.
 */

import type { ReactNode } from "react";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function Card({
  title,
  subtitle,
  right,
  children,
  className,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cx(
        "rounded-xl border border-slate-700/60 bg-slate-900/40 backdrop-blur",
        className,
      )}
    >
      {(title || right) && (
        <header className="flex items-start justify-between gap-3 border-b border-slate-700/50 px-4 py-3">
          <div>
            {title && (
              <h2 className="text-sm font-semibold tracking-wide text-slate-100 uppercase">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>
            )}
          </div>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Badge({
  children,
  className,
  title,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        className ?? "border-slate-600/60 bg-slate-800/60 text-slate-300",
      )}
    >
      {children}
    </span>
  );
}

const ID_STYLES: { prefix: RegExp; className: string; label: string }[] = [
  { prefix: /^E\d/, className: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30", label: "evidence" },
  { prefix: /^F\d/, className: "bg-cyan-500/10 text-cyan-300 border-cyan-500/30", label: "fact" },
  { prefix: /^W\d/, className: "bg-violet-500/10 text-violet-300 border-violet-500/30", label: "witness" },
  { prefix: /^(LAW|P)\d/, className: "bg-amber-500/10 text-amber-300 border-amber-500/30", label: "legal rule" },
  { prefix: /^JQ/, className: "bg-orange-500/10 text-orange-300 border-orange-500/30", label: "judge question" },
  { prefix: /^PR-/, className: "bg-rose-500/10 text-rose-300 border-rose-500/30", label: "prosecution argument" },
  { prefix: /^DF-/, className: "bg-sky-500/10 text-sky-300 border-sky-500/30", label: "defense argument" },
];

/** One record reference - evidence, fact, witness, law, or argument */
export function IdChip({ id }: { id: string }) {
  const style = ID_STYLES.find((entry) => entry.prefix.test(id));
  return (
    <span
      title={style ? `${style.label} ${id}` : id}
      className={cx(
        "inline-block rounded border px-1.5 py-0.5 font-mono text-[11px] leading-4",
        style?.className ??
          "border-slate-600/50 bg-slate-800/60 text-slate-300",
      )}
    >
      {id}
    </span>
  );
}

export function IdList({
  ids,
  label,
  empty,
}: {
  ids: string[];
  label?: string;
  empty?: string;
}) {
  if (ids.length === 0) {
    return empty ? (
      <span className="text-xs text-slate-500">{empty}</span>
    ) : null;
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {label && <span className="text-xs text-slate-500">{label}</span>}
      {ids.map((id) => (
        <IdChip key={`${label ?? ""}-${id}`} id={id} />
      ))}
    </span>
  );
}

/** A 0-1 score as a bar; used for reliability and confidence */
export function Meter({
  value,
  tone = "emerald",
}: {
  value: number;
  tone?: "emerald" | "amber" | "rose" | "slate";
}) {
  const tones = {
    emerald: "bg-emerald-400",
    amber: "bg-amber-400",
    rose: "bg-rose-400",
    slate: "bg-slate-400",
  };
  return (
    <span className="inline-flex h-1.5 w-20 overflow-hidden rounded-full bg-slate-700/70 align-middle">
      <span
        className={cx("h-full rounded-full", tones[tone])}
        style={{ width: `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` }}
      />
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-slate-700/70 px-4 py-6 text-center text-sm text-slate-500">
      {children}
    </p>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div>
      <dt className="text-xs tracking-wide text-slate-500 uppercase">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-200">{children}</dd>
    </div>
  );
}
