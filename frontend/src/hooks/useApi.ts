"use client";

/**
 * One read from the backend: its data, why it failed, and whether it is still
 * in flight. Small on purpose - the interesting state in this app is the live
 * run, not the reads around it.
 */

import { useCallback, useEffect, useState } from "react";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useApi<T>(
  load: () => Promise<T>,
  deps: React.DependencyList = [],
  options: { refreshMs?: number } = {},
): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  // The loader is rebuilt by the caller's deps, which is what drives a refetch.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    run()
      .then((value) => {
        if (cancelled) return;
        setData(value);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [run, nonce]);

  useEffect(() => {
    if (!options.refreshMs) return;
    const timer = setInterval(() => setNonce((n) => n + 1), options.refreshMs);
    return () => clearInterval(timer);
  }, [options.refreshMs]);

  return { data, error, loading, reload: () => setNonce((n) => n + 1) };
}
