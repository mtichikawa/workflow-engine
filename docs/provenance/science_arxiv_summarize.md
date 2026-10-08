# Provenance — science / summarize (abstract → title)

Specialist/config: **`summarize` @ scope `science`** — a net-new *capability* (compress prose to a short
faithful form). Harvester: `tools/harvest/arxiv_summarize.py` (reuses the arXiv classify candidates —
no new fetch).

- **Source** — arXiv (the papers already harvested for `classify @ science`).
- **Real label** — the paper's author-written **title** (the short form); the long text is its abstract.
  Task: distil the abstract into a one-line title.
- **Count** — 39 golds (abstract → title).
- **Date pulled** — 2026-07-21 (reuses `state/harvest/arxiv_candidates.json`).
- **Eval** — leave-one-out with a **lexical-recall** matcher (`_summarize_match`): fraction of the real
  title's significant words captured by the generated summary (substring-tolerant), pass at ≥ 0.4.
  `python tools/eval_scope.py summarize science` → **27/39 (69%)** on 2026-07-21 — **provisional** (below
  the 80% trusted bar; abstract→title is a hard compression and the recall bar is strict).
- **Honesty note** — a lexical-recall proxy, not semantic judgment; a brain-judge would be stronger but
  non-deterministic. Deliberately a single interpretable bar (captures ≥40% of the title's key words),
  not a tuned decimal to Goodhart. Real reference (the author's own title).
