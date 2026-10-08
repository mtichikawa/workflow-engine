# Provenance — science / classify (arXiv primary category)

Specialist/config: **`classify` @ scope `science`** (new *config* of `classify`, no new specialist).
Harvester: `tools/harvest/arxiv_classify.py`.

- **Source** — arXiv API (public, no auth). One combined query across all categories (per-category
  bursts get the client 503-throttled — the combined query avoids the burst).
- **Real label** — the paper's `primary_category`, assigned by the author at submission (arXiv requires
  self-categorization). Task: given title + abstract, predict the primary subject category. Ground
  truth is the author's own label.
- **Label space** — 7 cross-FIELD categories (distinct disciplines, not near-neighbors): cs.CL, math.PR,
  q-bio.NC, astro-ph.GA, econ.EM, eess.SP, cond-mat.supr-con.
- **Count** — 39 golds (6 each except q-bio.NC=3).
- **Date pulled** — 2026-07-21. Note: arXiv rate-limits rapid requests; the harvester uses a single
  combined query and may need a cooldown between runs.
- **License / redistribution** — arXiv metadata (title/abstract/category); abstracts are author-provided.
  arXiv metadata is CC0. Regenerable: rerun the harvester (mind the rate limit).
- **Eval (leave-one-out, isolated)** — `python tools/eval_scope.py classify science` → **38/39 (97%)**
  on 2026-07-21. One miss: predicted *eess.SP*, actual *cs.CL* (plausible signal-processing/NLP overlap).
  Above the trusted bar. No code change — a new config on real labels.
