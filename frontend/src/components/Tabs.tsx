"use client";

/** A row of tabs; the panels themselves decide what to show */

import { useState, type ReactNode } from "react";

import { cx } from "@/components/ui";

export interface Tab {
  id: string;
  label: string;
  badge?: ReactNode;
  content: ReactNode;
}

export function Tabs({
  tabs,
  initial,
  className,
}: {
  tabs: Tab[];
  initial?: string;
  className?: string;
}) {
  const [active, setActive] = useState(initial ?? tabs[0]?.id);
  const current = tabs.find((tab) => tab.id === active) ?? tabs[0];

  return (
    <div className={className}>
      <div
        role="tablist"
        className="flex flex-wrap gap-1 border-b border-slate-800 pb-2"
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={tab.id === current?.id}
            onClick={() => setActive(tab.id)}
            className={cx(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              tab.id === current?.id
                ? "bg-amber-500/15 text-amber-200"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200",
            )}
          >
            {tab.label}
            {tab.badge !== undefined && (
              <span className="ms-1.5 text-xs text-slate-500">{tab.badge}</span>
            )}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="pt-4">
        {current?.content}
      </div>
    </div>
  );
}
