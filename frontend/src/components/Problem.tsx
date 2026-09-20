/** Why a read failed, with the one instruction that usually fixes it */

import { API_URL } from "@/lib/api";

export function Problem({
  error,
  retry,
}: {
  error: string;
  retry?: () => void;
}) {
  const offline = error.includes("Cannot reach the simulation backend");
  return (
    <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-5">
      <h2 className="text-sm font-semibold text-rose-200">
        {offline ? "The simulation backend is not answering" : "Something went wrong"}
      </h2>
      <p className="mt-1 text-sm text-slate-300">{error}</p>
      {offline && (
        <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-950/70 p-3 text-xs text-slate-400">
          {`cd backend\npython -m app.cli serve\n\n# then set, if the API is elsewhere:\n# NEXT_PUBLIC_API_URL=${API_URL}`}
        </pre>
      )}
      {retry && (
        <button
          type="button"
          onClick={retry}
          className="mt-3 rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <p className="animate-pulse rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-6 text-sm text-slate-500">
      Loading {what}…
    </p>
  );
}
