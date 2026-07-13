# ROUTE — contested-boundary candidates for labeling (2A)

ROUTE is the weakest specialist on leave-one-out (~64–79%), and the misses cluster on genuinely
*contested* component boundaries — which is where more exemplars help most. Components:
`core · api · docs · build · ui · auth · other`.

**Integrity note.** These are candidate **inputs only, deliberately unlabeled.** The eval's value is
that its golds are *human-labeled* ground truth; contested cases are exactly where a fabricated label
would poison that. So the correct component (+ escalate) is Mike's call — label via the gate
(`engine train route` surfaces hard cases; the gate captures your corrections into
`state/examples/baseline/route.jsonl`). Once labeled, they become real golds and should firm up the LOO.

Each candidate names the boundary tension it probes.

| # | item (GitHub-issue style) | boundary tension | your label (component · escalate?) |
|---|---|---|---|
| 1 | `feat: public request signature changed; downstream callers must update their payloads` | **api vs core** — is it the surface contract or the engine behind it? | |
| 2 | `perf: incremental compilation caches stale type info until a clean rebuild` | **build vs core** — toolchain caching or the type system? | |
| 3 | `bug: autocomplete dropdown shows results the search endpoint no longer returns` | **ui vs api** — stale client render or a backend contract change? | |
| 4 | `bug: token refresh endpoint returns 500 under concurrent requests` | **auth vs api** — auth flow or general endpoint concurrency? | |
| 5 | `docs: README quickstart throws because the documented default was changed in code` | **docs vs core** — fix the docs or restore the default? | |
| 6 | `security: an unauthenticated user can read another org's audit log via a guessable id` | **auth + escalate** — likely `auth`, and a clear escalate=true probe | |

**How to convert once labeled:** append `{"input": {"item": <the item>, "components": [core,api,docs,
build,ui,auth,other]}, "output": {"component": <label>, "escalate": <bool>, "reasoning": <one line>}}`
to `state/examples/baseline/route.jsonl` (or let the gate do it), then re-check with
`engine eval` and `engine fit route --samples 3`.
