# Provenance — match across 3 domains (generality standard)

> **Publication status (2026-10).** This page records what was measured on 2026-07-23 and stays as
> that record. When the engine's source and golds went public, data that can't be redistributed moved
> to the private corpus (still used locally, not in this repo), and the TMDB-derived film domain was
> deleted — TMDB's API terms forbid using its content with an AI application. Now: public: general, communities · **deleted: film** (TMDB terms).
> So this capability is **below the ≥ 3 public-domain bar** until rebuilt on redistributable data
> (`tests/test_generality.py` lists it in `IN_PROGRESS`). Licenses: [`DATA-NOTICE.md`](../../DATA-NOTICE.md).

`match` (pairwise: are two items the same / do they belong together?) validated leave-one-out on **3
unrelated domains**. Binary exact-match matcher (general). All sets balanced 50/50.

| Domain | Scope | "Same" means (ground truth) | Golds | LOO | Harvester |
|---|---|---|---|---|---|
| film | `film` | same franchise / collection (TMDB) | 32 | 31/32 (97%) | tmdb_match.py |
| general | `general` | same real-world entity (Wikipedia redirects / aliases) | 32 | 31/32 (97%) | wikipedia_match.py |
| communities | `communities` | same topic community (StackExchange site) | 28 | 21/28 (75%) | stackexchange_match.py |

- **The finding: match's accuracy tracks how well-defined "same" is.** Crisp sameness — a shared franchise,
  or two names for one entity ("Mark Twain" ↔ "Samuel Clemens", filtered to genuine aliases that need world
  knowledge, not string overlap) — scores 97%. A looser grouping (same broad community) scores 75%. Both are
  well above the 50% balanced baseline, so match is general, not narrow.
- **A degenerate task was dropped, not counted.** `match @ legislation` ("same broad CRS policy area") scored
  50% = chance, with every miss a false-negative: two unrelated Health bills share an area but aren't
  meaningfully "the same," and the model correctly refuses to call them identical. That's an ill-posed match
  task (the ground truth isn't crisp sameness), so it was removed — not padded, not counted.
- **Sources tried and rejected for a crisp third domain:** StackExchange true-duplicate pairs (the ideal, but
  `closed_details.original_questions` wasn't reachable through the public filter path) and Open Library
  same-series (the `series` field comes back empty). Wikipedia entity aliases gave clean, crisp ground truth.
