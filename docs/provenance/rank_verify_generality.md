# Provenance — rank + verify across 3 domains (generality standard, Phase 2)

> **Publication status (2026-10).** This page records what was measured on 2026-07-23 and stays as
> that record. When the engine's source and golds went public, data that can't be redistributed moved
> to the private corpus (still used locally, not in this repo), and the TMDB-derived film domain was
> deleted — TMDB's API terms forbid using its content with an AI application. Now: rank — public: baseline (synthetic rows only) · private corpus: baseline real-issue rows, reviews (App Store) · **deleted: film** (TMDB terms). verify — public: baseline, weather · private corpus: cooking (TheMealDB recipe text).
> So this capability is **below the ≥ 3 public-domain bar** until rebuilt on redistributable data
> (`tests/test_generality.py` lists it in `IN_PROGRESS`). Licenses: [`DATA-NOTICE.md`](../../DATA-NOTICE.md).

The two original judgment capabilities that had only their baseline config, now validated on 3 unrelated
domains each.

## rank (score one item 0..1 on a dimension) — matcher: |predicted − gold| ≤ 0.25

| Domain | Scope | Dimension / gold | Golds | LOO | Harvester |
|---|---|---|---|---|---|
| baseline | `baseline` | the original curated scoring dimension | 15 | 15/15 (100%) | (seed golds) |
| film | `film` | audience rating, from title+premise (TMDB vote_average/10) | 32 | 32/32 (100%) | tmdb_rank.py |
| reviews | `reviews` | reviewer satisfaction, from review text (Apple App Store star rating) | 40 | 33/40 (82%) | applereviews_rank.py |

- Film golds sampled ACROSS the rating range (0.43–0.85) so a constant guess fails. Reviews balanced across
  all 5 star values. Misses cluster on 3-star (neutral) reviews the model reads as more negative — an honest,
  understandable error, still within-one-star most of the time.

## verify (check a subject against a standard → pass/fail) — matcher: verdict == gold

| Domain | Scope | Standard / gold | Golds | LOO | Harvester |
|---|---|---|---|---|---|
| baseline | `baseline` | the original curated standard | 10 | 8/10 (80%) | (seed golds) |
| cooking | `cooking` | "recipe uses ingredient X", vs the real ingredient list (TheMealDB) | 32 | 28/32 (88%) | mealdb_verify.py |
| weather | `weather` | "alert is a severe/extreme threat", vs the real NWS severity | 32 | 29/32 (91%) | nws_verify.py |

- Both balanced pass/fail. cooking judges from the instructions prose (not a checkbox), so it's a real
  inference, not a lookup — the fairness concern (an ingredient used but unnamed in the prose) didn't tank it.

**Verdict:** both rank and verify are general across three unrelated domains. With this, **every judgment
capability meets the ≥ 3 unrelated-domain bar** and `tests/test_generality.py` enforces it with an empty
IN_PROGRESS list.
