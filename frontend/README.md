# Court Simulation - Frontend

The visual courtroom dashboard (spec section 20): Next.js, TypeScript, and
Tailwind CSS over the Phase 9 HTTP API.

> **Research simulation only.** This system does not provide legal advice or
> determine real legal rights or obligations. The Republic of Arandia, its
> laws, cases, and parties are fictional.

## Running it

The backend has to be up first - the browser talks to it directly.

```bash
# terminal 1
cd backend
pip install -r requirements.txt
python -m app.cli serve            # http://127.0.0.1:8000

# terminal 2
cd frontend
npm install
npm run dev                        # http://localhost:3000
```

The API defaults to `http://127.0.0.1:8000`. Point it elsewhere with
`NEXT_PUBLIC_API_URL` in `.env.local` (see `.env.local.example`), and add that
origin to `CORS_ORIGINS` for the backend.

## The pages

| Route | |
|---|---|
| `/` | Case selection, and the simulations run so far |
| `/cases/[caseId]` | The record - facts, evidence, witnesses, laws, and what the rule engine computed - and the form that starts a simulation |
| `/runs` | Every run the server remembers |
| `/runs/[runId]` | The live courtroom: the bench, the timeline, the event feed, and every panel |
| `/rules` | The law of Arandia |

## Following a run

Starting a simulation returns a run ID at once; the trial itself is minutes of
model calls. `useRunStream` subscribes to `/api/runs/{id}/stream` with
`EventSource`, listening for each court event type by name (spec section 21).
If the stream cannot be kept open it falls back to polling
`/api/runs/{id}/events?after=N`, which returns the same numbered events, so
nothing is lost or repeated either way.

While a run is going, everything on screen comes from the events. The full
text of arguments, verdicts, and the audit arrives with the finished run - the
panels say which they are showing rather than filling gaps with guesses.

## Scripts

```bash
npm run dev         # development server
npm run build       # production build
npm run typecheck   # tsc --noEmit
npm test            # vitest
```

The tests need no backend: the panels are rendered from a real finished run
kept in `src/lib/__fixtures__/trial-run.json`, and the stream is driven by a
fake `EventSource`.
