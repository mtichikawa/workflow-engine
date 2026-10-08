# Provenance — extract across 3 domains (generality standard)

> **Publication status (2026-10).** This page records what was measured on 2026-07-23 and stays as
> that record. When the engine's source and golds went public, data that can't be redistributed moved
> to the private corpus (still used locally, not in this repo), and the TMDB-derived film domain was
> deleted — TMDB's API terms forbid using its content with an AI application. Now: public: history, weather · private corpus: cooking (TheMealDB recipe text).
> So this capability is **below the ≥ 3 public-domain bar** until rebuilt on redistributable data
> (`tests/test_generality.py` lists it in `IN_PROGRESS`). Licenses: [`DATA-NOTICE.md`](../../DATA-NOTICE.md).

`extract` (pull a list of structured facts from prose) validated leave-one-out on **3 unrelated
domains**. Matcher is fuzzy set-F1 (≥ 0.5, substring-tolerant) in all three (general).

| Domain | Scope | What's extracted / gold | Golds | LOO | Harvester |
|---|---|---|---|---|---|
| cooking | `cooking` | ingredients, vs the recipe's real ingredient list (TheMealDB) | 35 | 35/35 (100%) | mealdb_extract.py |
| history | `history` | named entities, vs the event's linked Wikipedia pages | 30 | 30/30 (100%) | wikipedia_extract.py |
| weather | `weather` | affected areas, vs the alert's structured areaDesc (NWS) | 30 | 29/30 (97%) | nws_extract.py |

- **Gold ≠ surface form, and it still works.** History golds are Wikipedia article titles ("2018
  Inter-Continental Hotel Kabul attack"), not how the text phrases them — the fuzzy set-F1 bridges it via
  word overlap, so the eval is fair without me massaging the golds.
- **Generality verdict** — extract pulls ingredients, historical entities, and geographic areas at ~97–100%
  each. General across unrelated prose types, not narrow.
