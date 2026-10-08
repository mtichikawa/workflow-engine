# Provenance — legislation / classify (bill policy area)

Specialist/config: **`classify` @ scope `legislation`** (new config of `classify`). Harvester:
`tools/harvest/congress_classify.py`. Key-gated: `CONGRESS_API_KEY`.

- **Source** — Congress.gov `/v3/bill/118/{hr,s}` list → per-bill detail for `policyArea` (2-step).
- **Real label** — the bill's official CRS `policyArea` (assigned by the Congressional Research
  Service). Task: given a bill's title, predict its policy area.
- **Label space** — the 6 most-populated areas from ~137 scanned bills (Crime & Law Enforcement,
  Government Operations & Politics, Health, Taxation, Armed Forces & National Security, Energy);
  36 bills, 6 each.
- **Date pulled** — 2026-07-21.
- **Eval** — `python tools/eval_scope.py classify legislation` → **27/36 (75%)** — **provisional** (below
  the 80% bar). Bill titles are often cryptic/political and policy areas genuinely overlap (a bill can be
  both Crime and Health) — an honestly hard classification, not over-tuned.
