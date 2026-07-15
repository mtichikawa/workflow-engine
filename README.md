# Workflow engine

**Describe a job in plain English. It builds a workflow out of small AI specialists, runs it,
and hands you back a result — staged for a human.**

Built from scratch. The core is pure Python standard library; the "brain" for the AI steps is a
swappable port — Claude CLI (free on a Max plan) or the Anthropic API.

**See it work → https://mtichikawa.github.io/workflow-engine/** · How it's built → [how-it-works.html](https://mtichikawa.github.io/workflow-engine/how-it-works.html)

---

## Do it yourself

**1 · Clone and install** — Python 3.11+, the core pulls in no third-party packages.

```bash
git clone https://github.com/mtichikawa/workflow-engine.git && cd workflow-engine
pip install -e .
```

**2 · Give it a brain** — pick one:

- **Claude CLI** (default, free on Max): install `claude`, sign in. Nothing to configure.
- **Anthropic API**: `pip install anthropic && export ANTHROPIC_API_KEY=…  ENGINE_BRAIN=api`

**3 · Describe a job — watch it build the workflow**

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
Add `--run --input "<text>" --auto` to run what it composed on your own input. Ask for something it
can't cover and it says so — it won't fake a capability.

**4 · Or run a ready-made recipe** on real data — each **stages** its result; nothing is ever sent.

```bash
# reads real open issues → classify · prioritize · route · draft a reply · verify it
python -m engine.cli run triage --repo vercel/next.js --limit 5

# pulls sources → pick an angle · write a short post in a brief's voice · check it's on-brand
python -m engine.cli run content --topic "why flaky tests erode trust" --brief "sharp technical founder" --auto

# writes, self-grades against a strict bar, and rewrites until it passes (the loop is the point)
python -m engine.cli run refine --topic "why on-call rotations burn people out" --auto
```

If a brain is missing, the engine tells you exactly how to fix it.

## Proof — run the receipts yourself

```bash
python -m engine.cli benchmark                  # the composer re-derives hand-built specialists from a
                                                #   description, scored against their REAL human-labeled evals
python -m engine.cli eval                        # per-specialist accuracy + leave-one-out
python examples/scripts/learning_loop_demo.py    # a weak specialist learns from a few examples: 4/8 -> 8/8, promoted
python -m engine.cli registry                    # every specialist, run count, and trust state
```

**Honest about what's what:** nine shared specialists are built and curated with evals
(`act · classify · fetch · rank · respond · review · route · verify · write`). Anything the composer
drafts on the fly is marked `[PROVISIONAL]` — untrusted until it earns an eval; validate it at the
gate before you rely on it. This is a portfolio engine, not a shipped product — a coherent, working
synthesis, not a novel one.

## Layout

| path | what |
|---|---|
| `engine/` | domain · ports · dispatcher · composer · validator · specialists · fewshot · registry · scope |
| `engine/recipes/` | `triage · content · refine · review` |
| `usecases/` | the interactive step-by-step explorers embedded in the site (triage · content · refine) |
| `examples/` · `evals/` · `tests/` | real runs & runnable demos · grading harness · tests |
| `docs/` | [`SPEC`](docs/SPEC.md) · [`control-flow`](docs/control-flow.md) · [`learning-loop`](docs/learning-loop.md) · [`RESULTS`](docs/RESULTS.md) · [`depth`](docs/depth.md) (the hard parts, honestly) |

Full CLI: `run · compose · board · view · replay · eval · fit · benchmark · train · review · capture · registry · costs`.

## Cost

Text is **$0** in development — the brain is Claude via the free CLI. `engine/core/brain.py` is a
swappable port; the Anthropic-API backend (`ENGINE_BRAIN=api`) is there for a deployment that needs
it. No paid LLM in the loop by default.
