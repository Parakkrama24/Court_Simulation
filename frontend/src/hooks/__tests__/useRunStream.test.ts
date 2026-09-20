/**
 * Following a run: the stream, and the polling fallback when it breaks.
 *
 * jsdom has no EventSource, so this drives a fake one - which is also the only
 * way to test what happens when a stream drops mid-trial.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useRunStream } from "@/hooks/useRunStream";
import type { CourtEvent } from "@/lib/types";

class FakeEventSource {
  static last: FakeEventSource | null = null;
  readonly listeners = new Map<string, EventListener[]>();
  closed = false;

  constructor(readonly url: string) {
    FakeEventSource.last = this;
  }

  addEventListener(name: string, listener: EventListener) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
  }

  close() {
    this.closed = true;
  }

  emit(name: string, data: unknown) {
    const message = new MessageEvent(name, { data: JSON.stringify(data) });
    for (const listener of this.listeners.get(name) ?? []) {
      listener(message);
    }
  }

  fail() {
    for (const listener of this.listeners.get("error") ?? []) {
      listener(new Event("error"));
    }
  }
}

const event = (partial: Partial<CourtEvent>): CourtEvent => ({
  stage: "PROSECUTION_OPENING",
  event_type: "AGENT_ARGUMENT",
  timestamp: "2026-09-20T08:00:00Z",
  ...partial,
});

const run = (status: string, extra: Record<string, unknown> = {}) => ({
  run_id: "r1",
  case_id: "CASE_001",
  mode: "court",
  status,
  current_stage: "",
  event_count: 0,
  created_at: "2026-09-20T08:00:00Z",
  started_at: "2026-09-20T08:00:00Z",
  finished_at: null,
  error: null,
  options: {},
  result: null,
  usage: {},
  ...extra,
});

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  FakeEventSource.last = null;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useRunStream", () => {
  it("loads the run and opens a stream for it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(run("running"))),
    );
    const { result } = renderHook(() => useRunStream("r1"));

    await waitFor(() => expect(result.current.run).not.toBeNull());
    expect(result.current.transport).toBe("stream");
    expect(FakeEventSource.last?.url).toContain("/api/runs/r1/stream");
  });

  it("collects the events the stream names", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json(run("running"))),
    );
    const { result } = renderHook(() => useRunStream("r1"));
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());

    act(() => {
      FakeEventSource.last!.emit(
        "CASE_LOADED",
        event({ stage: "CASE_INITIALIZATION", event_type: "CASE_LOADED" }),
      );
      FakeEventSource.last!.emit(
        "AGENT_ARGUMENT",
        event({ agent_id: "prosecution_agent", argument_ids: ["PR-OPEN-1"] }),
      );
    });

    expect(result.current.events.map((e) => e.event_type)).toEqual([
      "CASE_LOADED",
      "AGENT_ARGUMENT",
    ]);
    expect(result.current.status).toBe("running");
  });

  it("re-reads the run when the stream says it completed", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(run("running")))
      .mockResolvedValue(
        json(run("completed", { result: { judgment: {} }, finished_at: "x" })),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRunStream("r1"));
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());

    act(() => {
      FakeEventSource.last!.emit("run_completed", { status: "completed" });
    });

    // the result only exists once the run is over, so the hook re-reads it
    await waitFor(() =>
      expect(result.current.run?.result).toEqual({ judgment: {} }),
    );
    expect(result.current.status).toBe("completed");
    expect(result.current.transport).toBe("closed");
    expect(FakeEventSource.last!.closed).toBe(true);
  });

  it("falls back to polling when the stream breaks, resuming where it stopped", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("/events")) {
        expect(url).toContain("after=1");
        return json({
          run_id: "r1",
          status: "completed",
          events: [event({ event_type: "JUDGE_DECISION" })],
          next_index: 2,
        });
      }
      return json(run("running"));
    });
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);

    const { result } = renderHook(() => useRunStream("r1"));
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull());

    act(() => {
      FakeEventSource.last!.emit(
        "CASE_LOADED",
        event({ event_type: "CASE_LOADED" }),
      );
      FakeEventSource.last!.fail();
    });

    await waitFor(() =>
      expect(result.current.events.map((e) => e.event_type)).toEqual([
        "CASE_LOADED",
        "JUDGE_DECISION",
      ]),
    );
    expect(FakeEventSource.last!.closed).toBe(true);
  });

  it("reports a run that cannot be read", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "Unknown run 'r1'" }), {
          status: 404,
        }),
      ),
    );
    const { result } = renderHook(() => useRunStream("r1"));
    await waitFor(() =>
      expect(result.current.error).toBe("Unknown run 'r1'"),
    );
  });
});
