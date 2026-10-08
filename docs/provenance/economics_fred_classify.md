# Provenance — economics / classify (economic topic)

Specialist/config: **`classify` @ scope `economics`** (new config of `classify`). Harvester:
`tools/harvest/fred_classify.py`. Key-gated: `FRED_API_KEY`.

- **Source** — FRED `/fred/tags/series?tag_names=<tag>` (by popularity).
- **Real label** — the series' economic topic, from its FRED tag. Task: given a data series' title,
  predict its topic.
- **Label space** — GDP & Output, Prices & Inflation, Employment, Interest Rates, Housing, Trade
  (36 series, 6 each).
- **Date pulled** — 2026-07-21.
- **Eval** — `python tools/eval_scope.py classify economics` → **35/36 (97%)**. Trusted.
