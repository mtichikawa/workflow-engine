# Provenance — sequence across 3 domains (generality standard)

> **Publication status (2026-10).** This page records what was measured on 2026-07-23 and stays as
> that record. When the engine's source and golds went public, data that can't be redistributed moved
> to the private corpus (still used locally, not in this repo), and the TMDB-derived film domain was
> deleted — TMDB's API terms forbid using its content with an AI application. Now: public: history · private corpus: cooking (TheMealDB recipe text) · **deleted: film** (TMDB terms).
> So this capability is **below the ≥ 3 public-domain bar** until rebuilt on redistributable data
> (`tests/test_generality.py` lists it in `IN_PROGRESS`). Licenses: [`DATA-NOTICE.md`](../../DATA-NOTICE.md).

`sequence` (order a set) validated leave-one-out on **3 unrelated domains** — the generality bar. The
matcher is normalized Kendall tau ≥ 0.75 in all three (general, not domain-specific).

| Domain | Scope | Real order (ground truth) | Golds | LOO | Harvester |
|---|---|---|---|---|---|
| history | `history` | events by their actual year (Wikipedia on-this-day) | 24 | 23/24 (96%) | wikipedia_sequence.py |
| film | `film` | movies by release year (TMDB) | 20 | 19/20 (95%) | tmdb_sequence.py |
| cooking | `cooking` | a recipe's own step order (TheMealDB) | 20 | 19/20 (95%) | mealdb_sequence.py |

- **Sources** — Wikipedia REST (no auth) · TMDB (`TMDB_API_KEY`) · TheMealDB (no auth).
- **Neutral presentation** — every puzzle presents items alphabetically (uncorrelated with the true order);
  gold is the real order. The item text hides the ordering key (year not printed; steps not numbered).
- **Test-validity fix (film).** First cut scored 55% because popular movies cluster by year, so puzzles
  contained same-year ties whose gold order is arbitrary and unrecoverable. Fixed by sampling one movie per
  distinct year, spread ≥3 years apart, making "order by year" well-defined → 95%. This is a validity fix
  (the task was ill-posed), not tuning to the metric.
- **Generality verdict** — holds across chronology, release-ordering, and procedural step-ordering at ~95%
  each. Not narrow; genuinely general.
