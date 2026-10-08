# Provenance — art / classify (The Met department)

Specialist/config: **`classify` @ scope `art`** (a new *config* of the existing `classify` capability —
not a new specialist; the collapse rule in action). Harvester: `tools/harvest/met_art_classify.py`.

- **Source** — The Metropolitan Museum of Art Collection API (public, no auth).
  `GET /public/collection/v1/objects?departmentIds=<id>` → sample object IDs → `GET .../objects/<id>`.
- **Real label** — the object's catalogued `department`, assigned by Met curators. Ground truth is the
  museum's own catalog, never authored by me. Task: given title / medium / date / culture / period,
  predict which of the harvested departments holds the object.
- **Label space** — 6 departments actually harvested: Egyptian Art, Greek and Roman Art, Asian Art,
  Islamic Art, Arms and Armor, European Paintings. (Musical Instruments + Photographs yielded no
  objects with sufficient descriptive fields in sampling; a sampling tweak can add them later.)
- **Count** — 30 golds (5 per department). Balanced.
- **Date pulled** — 2026-07-21 (public source drifts; this freezes the snapshot of record).
- **License / redistribution** — Met Open Access metadata; we keep only short factual catalog fields
  (title, medium, date, culture, period, department). Facts, not copyrightable expression
  (Met Open Access is CC0). Regenerable: rerun the harvester.
- **Eval (leave-one-out, isolated to this scope)** — `python tools/eval_scope.py classify art` →
  **29/30 (97%)** on 2026-07-21. One miss: predicted *Asian Art*, actual *European Paintings* (a
  plausible confusion on a sparse-field object). Above the 80% trusted bar. The `classify` capability
  needed no code change — this is purely a new config validated on real labels.
