# Provenance — sports / forecast (match result)

Specialist/config: **`forecast` @ scope `sports`** — the FIRST net-new *capability* of the campaign (not
a classify config: the outcome isn't readable from the input, it's revealed after the match).
Harvester: `tools/harvest/football_forecast.py`.

- **Source** — football-data.co.uk open season CSV (no auth): English Premier League 2022-23, 380 games.
- **Real label** — the full-time result (FTR: H/D/A), recorded after the match. The situation given to
  the specialist is pre-match only (home team, away team, league, date) — the score is never shown.
- **Outcome space** — home win / draw / away win.
- **Count** — 40 golds sampled evenly across the season. Sample outcome distribution: away 17, draw 8,
  home 15 (so a naive always-majority baseline ≈ 42.5%; always-home ≈ 37.5%).
- **Date pulled** — 2026-07-21.
- **License / redistribution** — public sports results (facts). Team names + date + result. Regenerable.
- **Honesty note** — football results are high-variance; even bookmakers land ~50-55% on 3-way. This is a
  deliberately hard test. The point is a REAL forecast signal graded by reality, not an inflated number —
  the capability is validated if it beats the base rate.
- **Eval (leave-one-out, isolated)** — `python tools/eval_scope.py forecast sports` → **24/40 (60%)**
  on 2026-07-21, vs. ~42.5% always-majority / 37.5% always-home baselines — **beats chance by ~17 pts** on
  real team-strength signal. Misses cluster on predicting *home win* when the actual result was a draw or
  away win (the classic home bias; draws are the hardest call). Legitimate forecast signal on a
  high-variance domain — the capability is validated (not an inflated number).
