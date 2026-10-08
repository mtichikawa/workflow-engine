# Provenance — cooking / classify (cuisine)

Specialist/config: **`classify` @ scope `cooking`** (new *config* of `classify`, no new specialist).
Harvester: `tools/harvest/mealdb_classify.py`.

- **Source** — TheMealDB public test API (no auth). `filter.php?a=<Area>` → meal IDs → `lookup.php?i=<id>`.
- **Real label** — the dish's catalogued `strArea` (cuisine). Task: given dish name + ingredient list,
  predict the cuisine. Ground truth is the database's own cuisine tag, not authored by me.
- **Label space** — 5 cuisines harvested: Italian, Mexican, Japanese, Chinese, Greek. (Indian + French
  returned empty on the v1 test API.)
- **Count** — 30 golds (6 per cuisine). Balanced.
- **Date pulled** — 2026-07-21.
- **License / redistribution** — TheMealDB test API; we keep dish name + ingredients + cuisine (facts).
  Credit: see `DATA-NOTICE.md`. Regenerable: rerun the harvester.
- **Eval (leave-one-out, isolated)** — `python tools/eval_scope.py classify cooking` → **30/30 (100%)**
  on 2026-07-21. Above the trusted bar. No code change — a new config validated on real labels.
