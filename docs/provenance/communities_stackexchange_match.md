# Provenance — communities / match (same-community pair)

Specialist/config: **`match` @ scope `communities`** — a net-new *capability* (pairwise same-or-not).
Harvester: `tools/harvest/stackexchange_match.py` (reuses the StackExchange classify candidates — no new
fetch).

- **Source** — the StackExchange questions already harvested for `classify @ communities`.
- **Real label** — whether two questions came from the SAME community (their actual source sites).
  Task: given two question titles, decide same-community or not. Ground truth is where users posted them.
- **Count** — 28 pairs, balanced 14 same / 14 different. Positives = same site; negatives = different
  sites (adjacent sites like cooking/gardening, movies/scifi make negatives non-trivial).
- **Date pulled** — 2026-07-21 (reuses `state/harvest/stackexchange_candidates.json`).
- **Eval** — leave-one-out, exact boolean match (`same == same`). Clean binary.
  `python tools/eval_scope.py match communities` → **21/28 (75%)** on 2026-07-21 — **provisional**
  (below the 80% bar). Debugging note: the first cut scored 50% because the criteria said "same" and the
  model read it as "same *question*" (correctly calling two different cooking questions "not the same");
  rewording to "same SUBJECT AREA, not the same question" lifted it to 75%. Remaining misses are all
  same-community pairs on genuinely different sub-topics — a fuzzy "how broad is the same area" boundary.
  Negatives (different community) all pass. Not over-tuned.
- **Note** — same-community is a clean, reliable proxy for the pairwise-matching capability (dedup /
  entity-resolution / linking). True duplicate-close pairs are a richer future source (SE moderator
  decisions) but needed a fragile filter; this validates the capability cleanly today.
