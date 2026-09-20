"use client";

/**
 * The top bar: where you are, whether the backend is up, and the disclaimer
 * spec section 24 requires to be visible.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { API_URL, getHealth } from "@/lib/api";
import { DISCLAIMER } from "@/lib/court";
import type { HealthResponse } from "@/lib/types";
import { Badge, cx } from "@/components/ui";

const LINKS = [
  { href: "/", label: "Cases" },
  { href: "/rules", label: "Legal rules" },
  { href: "/runs", label: "Simulations" },
];

export function SiteHeader() {
  const pathname = usePathname();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const response = await getHealth();
        if (!cancelled) {
          setHealth(response);
          setDown(false);
        }
      } catch {
        if (!cancelled) setDown(true);
      }
    };
    void check();
    const timer = setInterval(check, 15000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <header className="mb-6 border-b border-slate-800/80 bg-slate-950/40">
      <div className="mx-auto flex w-full max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-4 sm:px-6">
        <Link href="/" className="flex items-center gap-3">
          <span aria-hidden className="text-2xl">
            ⚖️
          </span>
          <span>
            <span className="block font-[family-name:var(--font-display)] text-lg leading-5 text-slate-100">
              Court Simulation
            </span>
            <span className="block text-xs text-slate-500">
              Republic of Arandia (fictional)
            </span>
          </span>
        </Link>

        <nav className="flex items-center gap-1 text-sm">
          {LINKS.map((link) => {
            const active =
              link.href === "/"
                ? pathname === "/"
                : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cx(
                  "rounded-md px-3 py-1.5 transition-colors",
                  active
                    ? "bg-amber-500/15 text-amber-200"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200",
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="ms-auto flex items-center gap-2">
          {down ? (
            <Badge
              className="border-rose-500/40 bg-rose-500/10 text-rose-300"
              title={`No answer from ${API_URL}`}
            >
              <span className="size-1.5 rounded-full bg-rose-400" />
              Backend offline
            </Badge>
          ) : health ? (
            <Badge
              className="border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              title={`${API_URL} - ${health.phase}`}
            >
              <span className="size-1.5 rounded-full bg-emerald-400" />
              {health.cases} cases · {health.rules} rules
              {health.active_runs > 0 && ` · ${health.active_runs} running`}
            </Badge>
          ) : (
            <Badge>Checking backend…</Badge>
          )}
        </div>
      </div>

      <p className="border-t border-amber-500/20 bg-amber-500/5 px-4 py-1.5 text-center text-[11px] text-amber-200/80 sm:px-6">
        {DISCLAIMER}
      </p>
    </header>
  );
}
