# Workflow engine

**Describe a job in plain English. It composes a workflow out of small AI specialists, runs it,
and hands you back a result — staged for a human.**

Built from scratch: the composer, a validator, a coordination board with human gates, and a
learning loop that sharpens each specialist from a handful of examples. The core is pure standard
library; the "brain" for the AI steps is a swappable port (Claude CLI, free on Max — or the
Anthropic API).

## See it — no install

- **See it work** → https://mtichikawa.github.io/workflow-engine/ — describe a job, watch it compose and run.
- **How it's built** → https://mtichikawa.github.io/workflow-engine/how-it-works.html — the depth.
- **Real runs, click-through** → https://mtichikawa.github.io/workflow-engine/usecases/ — every value shown is from an actual logged run.

## The Composer — the one to try

Give it a plain-English task; it builds a workflow from the shared library — reusing what fits,
and honestly flagging what it doesn't have.

```bash
python -m engine.cli compose "read GitHub issues, label and prioritize them, and draft a first response"
```
```
Composed recipe for: 'read GitHub issues, label and prioritize them, and draft a first response'

  reuse  classify
  reuse  rank
  domn   respond
  reuse  act

runnable:  True
```

`reuse` shared capability · `domn` domain specialist · `DRFT` one it drafted for you ·
`NEW!` a gap it flags instead of faking · `[GATE]` a human-approval pause.

Ask for something it can't cover and it says so, with the missing specialist's input→output
contract — it won't fake a capability:

```bash
python -m engine.cli compose "transcribe support calls and summarize the action items"   # -> flags the gap
```

Add `--run --input "<text>" --auto` to run what it composed on your own input.

## Quickstart

Python 3.11+. The engine core pulls in no third-party packages.

```bash
git clone https://github.com/mtichikawa/workflow-engine.git && cd workflow-engine
pip install -e .

# give it a brain — pick one:
#   Claude CLI (default, free on Max): install `claude`, sign in. nothing to configure.
#   Anthropic API:  pip install anthropic && export ANTHROPIC_API_KEY=…  ENGINE_BRAIN=api

python -m engine.cli run triage --repo vercel/next.js --limit 5
```

If a brain is missing, the engine tells you exactly how to fix it.

## Three example recipes

Each takes real input, runs the specialists, and **stages** a result — nothing is ever sent automatically.

| recipe | what it does | run it |
|---|---|---|
| `triage` | reads real open GitHub issues → classify · prioritize · route · draft a reply · verify | `run triage --repo <owner/repo> --limit N` |
| `content` | pulls sources → pick an angle · write a short post in a brief's voice · check it's on-brand | `run content --topic "…" --brief "…" --auto` |
| `refine` | write → self-grade against a strict bar → **rewrite until it passes** (the loop is the point) | `run refine --topic "…" --auto` |

The [interactive explorers in the gallery](https://mtichikawa.github.io/workflow-engine/usecases/)
*are* these runs, click-through — the clearest way to watch one work end to end.

## Proof — run the receipts yourself

```bash
python -m engine.cli benchmark                  # the composer re-derives hand-built specialists from a
                                                #   description, scored against their REAL human-labeled evals
python -m engine.cli eval                        # per-specialist accuracy + leave-one-out
python examples/scripts/learning_loop_demo.py    # a weak specialist learns from a few examples: 4/8 -> 8/8, promoted
python -m engine.cli registry                    # every specialist, run count, and trust state
```

**Honest about what's what:** nine shared specialists are built and curated with evals
(`act · classify · fetch · rank · respond · review · route · verify · write`). Anything the
composer drafts on the fly is marked `[PROVISIONAL]` — untrusted until it earns an eval. Validate
at the gate before you rely on it. This is a portfolio engine, not a shipped product — a coherent,
working synthesis, not a novel one.

## Layout

| path | what |
|---|---|
| `engine/` | domain · ports · dispatcher · composer · validator · specialists · fewshot · registry · scope |
| `engine/recipes/` | `triage · content · refine · review` |
| `usecases/` | one self-contained bundle per use case (interactive explorer + I/O) + the gallery |
| `examples/` · `evals/` · `tests/` | real runs & runnable demos · grading harness · tests |
| `docs/` | [`SPEC`](docs/SPEC.md) · [`control-flow`](docs/control-flow.md) · [`learning-loop`](docs/learning-loop.md) · [`RESULTS`](docs/RESULTS.md) · [`depth`](docs/depth.md) (the hard parts, honestly) |

Full CLI: `run · compose · board · view · replay · eval · fit · benchmark · train · review · capture · registry · costs`.

## Cost

Text is **$0** in development — the brain is Claude via the free CLI. `engine/core/brain.py` is a
swappable port; the Anthropic-API backend (`ENGINE_BRAIN=api`) is there for a deployment that needs
it. No paid LLM in the loop by default.
