/** The client: what it sends, and what it does with an error */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  API_URL,
  ApiError,
  ApiUnreachableError,
  getCase,
  getEvents,
  listCases,
  parseEvent,
  startSimulation,
  streamUrl,
} from "@/lib/api";

const ok = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });

const stub = (response: Response | Error) => {
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => {
    if (response instanceof Error) throw response;
    return response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("reads", () => {
  it("asks the configured backend for the cases", async () => {
    const fetchMock = stub(ok([{ case_id: "CASE_001" }]));
    await expect(listCases()).resolves.toEqual([{ case_id: "CASE_001" }]);
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_URL}/api/cases`,
      expect.objectContaining({
        headers: expect.objectContaining({ "content-type": "application/json" }),
      }),
    );
  });

  it("escapes an id in the path", async () => {
    const fetchMock = stub(ok({}));
    await getCase("CASE 001/x");
    expect(fetchMock.mock.calls[0][0]).toBe(
      `${API_URL}/api/cases/CASE%20001%2Fx`,
    );
  });

  it("resumes an event page from an index", async () => {
    const fetchMock = stub(ok({ events: [], next_index: 7 }));
    await getEvents("run-1", 7);
    expect(fetchMock.mock.calls[0][0]).toBe(
      `${API_URL}/api/runs/run-1/events?after=7`,
    );
  });
});

describe("starting a simulation", () => {
  it("posts the options as the request body", async () => {
    const fetchMock = stub(ok({ run_id: "r1", status: "queued" }));
    await startSimulation("CASE_001", { mode: "court", jurors: 3 });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_URL}/api/cases/CASE_001/simulate`);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      mode: "court",
      jurors: 3,
    });
  });
});

describe("errors", () => {
  it("carries the backend's detail and status", async () => {
    stub(
      new Response(JSON.stringify({ detail: "Unknown case 'CASE_404'" }), {
        status: 404,
      }),
    );
    await expect(getCase("CASE_404")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "Unknown case 'CASE_404'",
    });
  });

  it("falls back to the status line when there is no detail", async () => {
    stub(new Response("nope", { status: 500, statusText: "Server Error" }));
    await expect(listCases()).rejects.toBeInstanceOf(ApiError);
  });

  it("says how to start the backend when it is not answering", async () => {
    stub(new TypeError("Failed to fetch"));
    const failure = await listCases().catch((cause) => cause);
    expect(failure).toBeInstanceOf(ApiUnreachableError);
    expect(failure.message).toContain("python -m app.cli serve");
  });
});

describe("streaming", () => {
  it("points EventSource at the run's stream", () => {
    expect(streamUrl("run 1")).toBe(`${API_URL}/api/runs/run%201/stream`);
  });

  it("parses an event, and survives a malformed one", () => {
    expect(
      parseEvent('{"stage":"JUDGE_DECISION","event_type":"JUDGE_DECISION"}'),
    ).toMatchObject({ event_type: "JUDGE_DECISION" });
    expect(parseEvent("half a mess")).toBeNull();
  });
});
