# Provenance — communities / classify (StackExchange site)

Specialist/config: **`classify` @ scope `communities`** (new *config* of `classify`, no new specialist).
Harvester: `tools/harvest/stackexchange_classify.py`.

- **Source** — StackExchange API (public, no auth, rate-limited). `/2.3/questions?site=<site>&sort=votes`.
- **Real label** — the StackExchange SITE the question was actually asked on. Task: given a question
  title, predict its community. Ground truth is where users really posted it.
- **Label space** — 7 deliberately-unrelated communities: Cooking, Law, Movies & TV, History, Gardening,
  Travel, Science Fiction & Fantasy. One config spanning wholly different fields — a clean demonstration
  that `classify` is niche-agnostic.
- **Count** — 49 golds (7 per community). Balanced.
- **Date pulled** — 2026-07-21.
- **License / redistribution** — question titles (CC-BY-SA on SE); we keep title + community. Regenerable.
- **Eval (leave-one-out, isolated)** — `python tools/eval_scope.py classify communities` → **46/49
  (94%)** on 2026-07-21. Plausible misses (Gardening/Cooking, Movies/SciFi — genuinely overlapping).
  Above the trusted bar. One config classifying across 7 unrelated fields.
