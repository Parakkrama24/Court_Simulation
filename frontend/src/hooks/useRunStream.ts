"use client";

/**
 * Follow a run as it happens.
 *
 * The backend streams Server-Sent Events whose message names are the court
 * event types (spec section 21), so each one is subscribed by name. If the
 * browser cannot keep a stream open, the hook falls back to polling
 * `/events?after=N`, which returns exactly the same events - the backend
 * numbers them, so nothing is lost or repeated either way.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  STREAM_EVENT_NAMES,
  getEvents,
  getRun,
  isTerminal,
  parseEvent,
  streamUrl,
} from "@/lib/api";
import type { CourtEvent, RunDetail, RunStatus } from "@/lib/types";

export type Transport = "stream" | "polling" | "closed";

export interface RunStream {
  run: RunDetail | null;
  events: CourtEvent[];
  status: RunStatus;
  transport: Transport;
  error: string | null;
  /** Re-read the run, for a manual refresh */
  refresh: () => void;
}

const POLL_MS = 1500;

export function useRunStream(runId: string): RunStream {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [events, setEvents] = useState<CourtEvent[]>([]);
  const [status, setStatus] = useState<RunStatus>("queued");
  const [transport, setTransport] = useState<Transport>("stream");
  const [error, setError] = useState<string | null>(null);

  // How many events have been taken, so a fallback poll resumes exactly here.
  const received = useRef(0);
  const finished = useRef(false);

  const loadRun = useCallback(async () => {
    try {
      const detail = await getRun(runId);
      setRun(detail);
      setStatus(detail.status);
      if (detail.error) setError(detail.error);
      return detail;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      return null;
    }
  }, [runId]);

  const append = useCallback((incoming: CourtEvent[]) => {
    if (incoming.length === 0) return;
    received.current += incoming.length;
    setEvents((current) => [...current, ...incoming]);
  }, []);

  // The run itself: its options, and its result once it is finished.
  useEffect(() => {
    finished.current = false;
    received.current = 0;
    setEvents([]);
    setRun(null);
    setError(null);
    void loadRun();
  }, [runId, loadRun]);

  // The live stream.
  useEffect(() => {
    let source: EventSource | null = null;
    let poller: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;
    // A stream always replays a run from its first event, so this connection
    // owns the list while it is open. That also makes a reconnect - or React's
    // double-mount in development - replace the events rather than double them.
    const streamed: CourtEvent[] = [];

    const end = async (nextStatus: RunStatus) => {
      finished.current = true;
      setStatus(nextStatus);
      setTransport("closed");
      source?.close();
      if (poller) clearTimeout(poller);
      // The result only exists once the run is over.
      await loadRun();
    };

    const poll = async () => {
      if (stopped || finished.current) return;
      try {
        const page = await getEvents(runId, received.current);
        append(page.events);
        setStatus(page.status);
        setError(null);
        if (isTerminal(page.status)) {
          await end(page.status);
          return;
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause));
      }
      if (!stopped && !finished.current) {
        poller = setTimeout(poll, POLL_MS);
      }
    };

    const fallBackToPolling = () => {
      if (stopped || finished.current) return;
      setTransport("polling");
      source?.close();
      source = null;
      void poll();
    };

    try {
      source = new EventSource(streamUrl(runId));
    } catch {
      fallBackToPolling();
      return () => {
        stopped = true;
        if (poller) clearTimeout(poller);
      };
    }

    const onCourtEvent = (message: MessageEvent<string>) => {
      const event = parseEvent(message.data);
      if (!event) return;
      streamed.push(event);
      received.current = streamed.length;
      setEvents([...streamed]);
      setStatus("running");
      setError(null);
    };

    for (const name of STREAM_EVENT_NAMES) {
      source.addEventListener(name, onCourtEvent as EventListener);
    }
    source.addEventListener("run_completed", () => void end("completed"));
    source.addEventListener("run_failed", () => void end("failed"));
    source.addEventListener("error", () => {
      // EventSource reconnects on its own, but the browser gives no reason
      // for the failure; polling is the honest fallback once the run is not
      // already over.
      if (finished.current) return;
      fallBackToPolling();
    });

    return () => {
      stopped = true;
      source?.close();
      if (poller) clearTimeout(poller);
    };
  }, [runId, append, loadRun]);

  return {
    run,
    events,
    status,
    transport,
    error,
    refresh: () => void loadRun(),
  };
}
