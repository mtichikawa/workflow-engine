# Workflow engine

A general **workflow-automation engine**, built from scratch: small AI **specialists** that each do one
job, composed into validated **control-flow graphs** (recipes), coordinated on a **board** by a
**dispatcher**, with **human gates** and a **learning loop** that improves each specialist from a handful
of examples. Niche-agnostic — the *same core* runs support-triage, content, and a quality-refinement loop.

> The Python package is named **`engine`** (the working name). This repo holds the **source**, the
> **docs**, and the **live site** (served via GitHub Pages).

## See it (no code)
- **Live writeup → https://mtichikawa.github.io/workflow-engine/** — what it is, how you use it, a real run.
- **Use-case gallery → https://mtichikawa.github.io/workflow-engine/usecases/** — click through real runs,
  step by step: triage · content · refine (the loop). Every value is from an actual logged run.

## Try it
```bash
pip install -e .

python -m engine.cli run triage --repo vercel/next.js --limit 5   # triage real GitHub issues (staged)
python -m engine.cli run content --topic "why flaky tests erode trust" --auto
python -m engine.cli compose "screen incoming support emails and draft replies"   # Composer builds a recipe
python -m engine.cli replay <run_id>                              # HTML animation of a run
python examples/proof_shared.py                                  # the reuse proof (same specialists, many recipes)
python examples/learning_loop_demo.py                            # a specialist learns: 4/8 -> 8/8, promoted
```
Full CLI: `run · compose · replay · board · view · eval · fit · benchmark · train · review · capture · registry · costs`.

## The idea in one breath
Most judgment work has the same shape:
```
FETCH → CLASSIFY → RANK → [ DOMAIN MIDDLE ] → VERIFY → ACT ⏸
└──────── shared capability-specialists ────────┘   (only the middle differs)
```
Shared bookends + a swappable middle = modular. The **Composer** builds a recipe, the **Validator**
checks the graph *before* it runs, the **Dispatcher** runs it item-by-item on the board, and a
**learning loop** teaches each specialist from curated examples (few-shot, not fine-tuning).

## Where things are
| path | what |
|---|---|
| `engine/` | the engine — domain · ports · dispatcher · composer · validator · specialists · fewshot · registry · scope |
| `engine/recipes/` | the recipe definitions (triage · content · refine · review) |
| `usecases/` | one self-contained bundle per use case (interactive explorer + example I/O) + the gallery |
| `examples/` | runnable demos — `python examples/<name>.py` |
| `evals/` · `tests/` | grading harness · 40 tests |
| `tools/` | the site/explorer generators (`build_explorer.py`, `build_gallery.py`) |
| `deploy/` | container-per-customer security **design** (skeleton, not run) |
| `docs/` | documentation (below) |
| `index.html` | the live writeup page (GitHub Pages) |
| `state/` `output/` `logs/` | runtime + generated artifacts — **gitignored, disposable** |

## Docs
- **Architecture:** [`SPEC.md`](docs/SPEC.md) · [`control-flow.md`](docs/control-flow.md) · lexicon [`glossary.md`](docs/glossary.md)
- **Learning loop:** [`learning-loop.md`](docs/learning-loop.md) · measured results [`RESULTS.md`](docs/RESULTS.md)
- **The hard parts, honestly:** [`depth.md`](docs/depth.md)
- **The visualization system:** [`visualization.md`](docs/visualization.md)
- **Tracking:** [`known-issues.md`](docs/known-issues.md) · [`cost-model.md`](docs/cost-model.md) · [`route-contested-candidates.md`](docs/route-contested-candidates.md)

## Cost
Text is **$0** — the brain is Claude via the free CLI. `engine/core/brain.py` is a swappable port; an
Anthropic-API backend is already coded (`ENGINE_BRAIN=api`) for when a deployment needs it. No paid LLM
in the loop for development.
