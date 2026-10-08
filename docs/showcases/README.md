# Showcases — the product working end-to-end on real data

Each showcase is a plain-English job → the Composer builds a recipe from the library (reusing
capabilities via their cards, no cloning) → it runs on **real, fresh** input → real output. These are
the depth complement to the per-capability provenance in `docs/provenance/`. All reproducible from the CLI.

Reproduce: `python -m engine.cli --scope <scope> compose "<job>" --run --input "<real text>" --auto`

---

## 1 · Cooking assistant — `extract` + `classify` (scope `cooking`)

**Job:** "Given a recipe's cooking instructions, extract the list of ingredients used and identify the
dish's cuisine."
**Composed:** `reuse extract` → `reuse classify` (zero drafts).
**Input:** a fresh random TheMealDB recipe — *Rigatoni with fennel sausage sauce* (real cuisine: Italian).
**Ran:**
- `extract` → `["oil","sausage","onion","fennel","paprika", …]` — pulled the ingredients out of the prose.
- `classify` → `{"label":"italian","confidence":0.93}` — **correct** (real cuisine was Italian).

## 2 · Research-paper triage — `classify` + `summarize` (scope `science`)

**Job:** "Given a research paper's abstract, identify its arXiv subject category and write a one-line
title capturing its core contribution."
**Composed:** `reuse classify` → `reuse summarize` (zero drafts).
**Input:** a fresh arXiv abstract (real primary category `q-bio.NC`).
**Ran:**
- `classify` → `{"label":"q-bio"}` — right field (quantitative biology / neuroscience).
- `summarize` → generated a one-line title from the abstract.

## 3 · Museum acquisitions triage — `classify` + `forecast` + `rank` + `act`, WITH control flow (scope `art`)

**Job:** "Each morning, categorize new museum acquisition offers by curatorial department, predict which
will draw the biggest crowds, and stage a digest of the top few."
**Composed:** `reuse classify → forecast → rank → summarize → act[GATE] ×2` with real branches:
department-scope gate · a draw gate · a priority threshold (>0.6) · dead-end coverage to a holding stage.
**Input:** a real Met object — Van Gogh, *Wheat Field with Cypresses* (real dept: European Paintings).
**Ran (branching fired correctly):**
- `classify` → `paintings` (0.97) ✓ · `forecast` → `blockbuster_draw` (a Van Gogh) · `rank` → 0.55.
- priority **0.55 ≤ 0.6**, so the negative branch routed to `stage_holding`; the digest steps were
  correctly **skipped**; the `act` gate auto-approved and staged the record. The control flow worked —
  the else-path is covered, no dead-ends.

---

**What these prove:** the Composer reads the capability cards and **reuses** the library (never cloned a
per-domain specialist), wires valid multi-step control flow, and the whole thing **runs on real data**
with sensible results — the "describe a job → it builds and runs the workflow" promise, demonstrated,
across three unrelated domains reusing the same expanded library.
