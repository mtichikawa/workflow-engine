# Provenance — summarize across 3 domains (generality standard)

> **Publication status (2026-10).** This page records what was measured on 2026-07-23 and stays as
> that record. When the engine's source and golds went public, data that can't be redistributed moved
> to the private corpus (still used locally, not in this repo), and the TMDB-derived film domain was
> deleted — TMDB's API terms forbid using its content with an AI application. Now: public: science, general · private corpus: communities (full Stack Exchange question bodies).
> So this capability is **below the ≥ 3 public-domain bar** until rebuilt on redistributable data
> (`tests/test_generality.py` lists it in `IN_PROGRESS`). Licenses: [`DATA-NOTICE.md`](../../DATA-NOTICE.md).

`summarize` (compress prose to a short faithful form) validated leave-one-out on **3 unrelated domains**.
Same lexical-recall matcher in all three (fraction of the reference's significant words captured, ≥ 0.4),
so the numbers are directly comparable.

| Domain | Scope | Long form → real short form (gold) | Golds | LOO | Harvester |
|---|---|---|---|---|---|
| science | `science` | arXiv abstract → paper title | 39 | 27/39 (69%) | arxiv_summarize.py |
| communities | `communities` | StackExchange question body → its title | 30 | 23/30 (77%) | stackexchange_summarize.py |
| general | `general` | Wikipedia lead paragraph → one-line description | 35 | 28/35 (80%) | wikipedia_summarize.py |

- **Consistent ~70–80% across unrelated prose** (academic, Q&A, general-knowledge) — summarize is general,
  not narrow. It's honestly a harder capability than the exact-match ones because compression is judged on
  strict lexical recall, not exact equality.
- **Not tuned.** Same metric across all three; the band reflects genuine task difficulty, not per-domain
  fiddling. science sits below the 80% bar, communities near it, general at it.
- A semantic-judge metric would likely score all three higher and more fairly, but it's non-deterministic;
  the lexical-recall proxy is the honest, deterministic floor.
