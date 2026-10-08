# Provenance — forecast across 3 domains (generality standard)

> **Publication status (2026-10).** This page records what was measured on 2026-07-23 and stays as
> that record. When the engine's source and golds went public, data that can't be redistributed moved
> to the private corpus (still used locally, not in this repo), and the TMDB-derived film domain was
> deleted — TMDB's API terms forbid using its content with an AI application. Now: public: sports, legislation · **deleted: film** (TMDB terms).
> So this capability is **below the ≥ 3 public-domain bar** until rebuilt on redistributable data
> (`tests/test_generality.py` lists it in `IN_PROGRESS`). Licenses: [`DATA-NOTICE.md`](../../DATA-NOTICE.md).

`forecast` (predict an unknown/future outcome, reality grades it) validated leave-one-out on **3
unrelated domains**. Matcher is exact prediction match in all three (general).

**How forecast is judged:** not against the 80% trusted bar — a perfect forecaster of genuinely uncertain
outcomes still scores well under 80%. The honest bar for a forecaster is **beating the baseline** (the
best you can do without the situation). All three clear it.

| Domain | Scope | Outcome (ground truth) | Golds | Baseline | LOO | Harvester |
|---|---|---|---|---|---|---|
| sports | `sports` | EPL match result, score hidden (3-way) | 40 | ~42% (always-majority) | 24/40 (60%) | football_forecast.py |
| film | `film` | audience reception, rating hidden (binary) | 32 | 50% (balanced) | 22/32 (69%) | tmdb_forecast.py |
| legislation | `legislation` | bill became law in the 117th (binary) | 32 | 50% (balanced) | 19/32 (59%) | congress_forecast.py |

- **Situation hides the outcome** — no score, no rating, no final status in the input; the specialist
  predicts from pre-outcome facts (teams; title+premise; bill title).
- **Signal is real but modest in each** — team strength, film premise, and bill-naming/topic cues
  respectively. legislation is the hardest (most passage signal isn't in the title) and honestly lands
  lowest, still +9 over chance.
- **Generality verdict** — forecast extracts real signal in three unrelated outcome spaces (sports, film,
  legislation); it is general, not narrow. Inherently below 80% because the outcomes are genuinely
  uncertain — that is the nature of forecasting, not a defect.
