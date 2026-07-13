# Workflow engine

A general **workflow-automation engine**, built from scratch: small AI **specialists** that each do one
job, composed into validated **recipes**, run on a coordination **board** with **human gates** and a
**learning loop** that sharpens each specialist from a handful of examples. Describe a job in plain
English — it builds the workflow, runs it, and hands you back a result, staged for a human.

> The Python package is named **`engine`** (working name). This repo holds the **source**, the **docs**,
> and the **live site**. For *how it works* and step-by-step interactive runs, see the site 👇

## See it live — no install
- **Writeup → https://mtichikawa.github.io/workflow-engine/** — what it is, how you use it, a real run.
- **Use-case gallery → https://mtichikawa.github.io/workflow-engine/usecases/** — click through real runs
  step by step: triage · content · refine (the loop). Every value shown is from an actual logged run.

## Get started

Requires **Python 3.11+** and a "brain" for the AI steps. The engine itself is **pure standard library**
— `pip install -e .` pulls in nothing else.

```bash
# 1. clone
git clone https://github.com/mtichikawa/workflow-engine.git
cd workflow-engine

# 2. install the `engine` package (no third-party deps)
pip install -e .

# 3. give it a brain — pick ONE:

#  (a) Claude CLI  — free on a Max plan, and the DEFAULT. Install the `claude` CLI,
#      sign in, and you're done. Nothing to configure.

#  (b) Anthropic API — billed, ~cents per run:
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...     # get one at console.anthropic.com
export ENGINE_BRAIN=api                 # optional: ENGINE_BRAIN_MODEL=claude-sonnet-4-5

# 4. run something (see below)
python -m engine.cli run triage --repo vercel/next.js --limit 5
```

If a brain is missing, the engine tells you exactly how to fix it (`claude CLI not found on PATH`, or
`api provider requires pip install anthropic`, or the Anthropic SDK asking for `ANTHROPIC_API_KEY`).

## Try it — run real workflows

`triage`, `content`, and `refine` are the three example recipes. Each takes real input, runs the
specialists, and **stages** a result for a human — nothing is ever sent automatically. Every command is
yours to change.

### `triage` — a support inbox that reads itself
```bash
python -m engine.cli run triage --repo vercel/next.js --limit 5
```
- **Does:** pulls 5 real open issues from the repo; for each one classifies it, scores urgency, routes it
  to a component, drafts a first reply, verifies that reply, and stages the lot.
- **You get:** a board summary in your terminal — each item's label, priority, route, and the staged
  action (labels + drafted reply). The **run id** is printed at the end.
- **Where:** the whole run is saved to `state/<run_id>.json`; staged actions append to
  `output/staged.jsonl`. Re-inspect any run with `python -m engine.cli board <run_id>`.
- **Your turn:** point `--repo` at *any* public GitHub repo, set `--limit N`:
  ```bash
  python -m engine.cli run triage --repo psf/requests --limit 8
  python -m engine.cli run triage --repo pallets/flask --limit 3
  ```

### `content` — research, then write a post
```bash
python -m engine.cli run content --topic "why flaky tests erode trust" \
    --brief "sharp, no-hype technical founder" --auto
```
- **Does:** pulls real sources, picks an angle, writes a short post in the brief's voice, checks it's
  on-brand, and stages it. `--auto` flows straight through the human gate.
- **You get:** the drafted post written under `output/` (and appended to `output/staged.jsonl`); the board
  summary in your terminal.
- **Inputs:** `--topic "<anything>"` is the subject, `--brief "<voice>"` sets the tone:
  ```bash
  python -m engine.cli run content --topic "what a compiler actually does" \
      --brief "patient teacher, concrete examples" --auto
  ```

### `refine` — draft, self-grade, rewrite until it passes (the loop)
```bash
python -m engine.cli run refine --topic "why on-call rotations burn people out" --auto
```
- **Does:** writes a draft, grades it against a strict bar, and — if it falls short — **rewrites and
  re-checks until it passes**. The loop is the whole point.
- **You get:** the final post plus the pass-by-pass trail (best seen in the gallery, below).

> **Watch a run, step by step:** the interactive explorers in the
> [gallery](https://mtichikawa.github.io/workflow-engine/usecases/) *are* these runs, click-through —
> the clearest way to see one work end to end.

## Try the Composer — describe *your* job, watch it build the workflow

This is the one to play with. Give it a plain-English task; it **composes a workflow** out of the shared
library of specialists — reusing what fits, and honestly flagging what it doesn't have.

```bash
python -m engine.cli compose "screen incoming support tickets, draft replies, and flag the urgent ones"
```
It prints the recipe it built — every step tagged, any gaps, the control-flow edges, and whether it's
runnable:
```
Composed recipe for: 'screen incoming support tickets, draft replies, and flag the urgent ones'

  reuse  classify
  reuse  rank
  reuse  respond
  reuse  verify
  reuse  act            [GATE]

runnable:  True
```
**Reading the tags:** `reuse` = an existing shared specialist, used as-is · `NEW!` = a capability it
needs but doesn't have — it flags it instead of faking it · `DRFT` = a provisional specialist it drafted
for you · `[GATE]` = a human-approval pause.

**Examples to try:**
```bash
# reuses the library cleanly  ->  runnable: True
python -m engine.cli compose "read GitHub issues, label and prioritize them, and draft a first response"

# hits a gap  ->  it flags the missing specialist (with its input->output contract) and won't fake it
python -m engine.cli compose "transcribe support calls and summarize the action items"

# YOUR workflow — any judgment-heavy, multi-step task:
python -m engine.cli compose "<describe your workflow in plain English>"
```

**Run what it composed** (when it's runnable), on your own input:
```bash
python -m engine.cli compose "screen support tickets and draft replies" \
    --run --input "Your API returns 500 on every POST since this morning — this is blocking our launch." --auto
```
- `--run` runs the composed recipe · `--input "<text>"` is the work-item · `--auto` auto-approves the gate.
- **You get:** the recipe runs on your input and stages a result, saved to `state/composed-<run_id>.json`.
- **Fill gaps automatically:** add `--draft` and it drafts provisional specialists for any missing pieces
  so it runs end-to-end (untrusted — validate at the gate before you rely on them).

## Proof it works — run the receipts yourself
```bash
python -m engine.cli benchmark         # re-derives hand-built specialists from a description, scores vs
                                       #   their REAL human-labeled evals — the composer matched them
python -m engine.cli eval              # every specialist's accuracy + leave-one-out over curated examples
python -m engine.cli registry          # every specialist, its run count + eval score
python examples/learning_loop_demo.py  # a weak specialist learns from a handful of examples: 4/8 -> 8/8, promoted
python examples/proof_shared.py        # the reuse proof — the same specialists across different recipes
```
Full CLI: `run · compose · board · view · approve · eval · fit · benchmark · train · review · capture · registry · costs`.

## Where things are
| path | what |
|---|---|
| `engine/` | the engine — domain · ports · dispatcher · composer · validator · specialists · fewshot · registry · scope |
| `engine/recipes/` | the recipe definitions (triage · content · refine · review) |
| `usecases/` | one self-contained bundle per use case (interactive explorer + example I/O) + the gallery |
| `examples/` | runnable demos — `python examples/<name>.py` |
| `evals/` · `tests/` | grading harness · tests |
| `tools/` | the site/explorer generators (`build_explorer.py`, `build_gallery.py`) |
| `deploy/` | container-per-customer security **design** (skeleton, not run) |
| `docs/` | documentation (below) |
| `index.html` | the live writeup page (GitHub Pages) |
| `state/` · `output/` | run boards + staged results land here — **gitignored, disposable** |

## Docs
- **Architecture:** [`SPEC.md`](docs/SPEC.md) · [`control-flow.md`](docs/control-flow.md) · lexicon [`glossary.md`](docs/glossary.md)
- **Learning loop:** [`learning-loop.md`](docs/learning-loop.md) · measured results [`RESULTS.md`](docs/RESULTS.md)
- **The hard parts, honestly:** [`depth.md`](docs/depth.md)
- **The visualization system:** [`visualization.md`](docs/visualization.md)
- **Tracking:** [`known-issues.md`](docs/known-issues.md) · [`cost-model.md`](docs/cost-model.md) · [`route-contested-candidates.md`](docs/route-contested-candidates.md)

## Cost
Text is **$0** in development — the brain is Claude via the free CLI. `engine/core/brain.py` is a
swappable port; the Anthropic-API backend (`ENGINE_BRAIN=api`) is there for a deployment that needs it.
No paid LLM in the loop by default.
