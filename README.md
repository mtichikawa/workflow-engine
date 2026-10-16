# Workflow engine

**Describe a job in plain English. It builds a workflow out of small AI specialists, runs it,
and hands you back a result — staged for a human.**

Built from scratch. The core is pure Python standard library; the "brain" for the AI steps is a
swappable port — Claude CLI (no per-call cost on a Max plan) or the Anthropic API.

**See it work → https://mtichikawa.github.io/workflow-engine/** · How it's built → [the How it works page](https://mtichikawa.github.io/workflow-engine/#how) · Every number, how it was measured → [docs/blind-evals.md](docs/blind-evals.md)

---

## Do it yourself

**1 · Clone and install** — Python 3.11+, the core pulls in no third-party packages.

```bash
git clone https://github.com/mtichikawa/workflow-engine.git && cd workflow-engine
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # or  pip install -e '.[mcp]'  for MCP interop (optional)
```

**2 · Give it a brain** — pick one:

- **Claude CLI** (default, no per-call cost on Max): install `claude`, sign in. Nothing to configure.
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
  reuse  act             [GATE]

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
python evals/blind.py triage                     # + routing · validator · composer: blind, sealed test sets with 95% CIs
```

**Honest about what's what:** fifteen library specialists are built — eight judgment capabilities
(`classify · rank · verify · forecast · extract · summarize · sequence · match`), I/O adapters
(`fetch · act · mcp_call`) and domain specialists (`respond · review · route · write`). Judgment
capabilities are graded leave-one-out on real, externally labeled public data; the standard is
≥ 3 unrelated domains each (`docs/standards.md`). Today `classify` clears it on 10 public domains; the
others sit at 1–2 *public* domains while data that couldn't be redistributed is replaced — run
`python tools/check_generality.py` for the live standing, and see `DATA-NOTICE.md` for what was
withheld and why. Anything the composer drafts on the fly is marked `[PROVISIONAL]` — untrusted until
it earns an eval; validate it at the gate before you rely on it. This is a portfolio engine, not a
shipped product — a coherent, working synthesis, not a novel one.

**Speaks MCP, both directions:** any external MCP tool can be a step (`mcp_call`), and every
specialist is exported as an MCP tool (`python -m engine.mcp.server`) — so Claude Desktop or any MCP
client can drive it. Runnable demos in `examples/`; walkthrough in [`docs/mcp.md`](docs/mcp.md).

**Watch it in a browser — a worked healthcare case:** `pip install -e '.[live]'` then
`python -m engine.live serve` and open `http://localhost:8600`. A doula-care intake on **synthetic**
documents shaped like the real ones (a faxed referral as an image-only PDF, phone photos of an insurance
card, an intake-form PDF, a visit-log CSV, a patient's chat message): the composer drafts the workflow
live — each draft, the validator's verdict on it and any repair shown as they happen — then the reviewed
recipe runs on the board, drawn as the full graph with each step's result and its input and output, and
it stops at a real Approve / Reject gate with a CMS-1500 claim draft, a patient reply and a clinical
handoff rendered as documents. The model reads the scans; plan rules, the claim form and the safety
sentence are plain code; anything medical in the message goes to a person, never answered by the model.
Nothing is ever sent. A **replay** mode re-runs the same engine against a recorded tape of the model's
answers (`engine/core/tape.py`), so the result is identical run to run; `python -m engine.live check`
verifies the tape still matches.

## Layout

| path | what |
|---|---|
| `engine/` | domain · ports · dispatcher · composer · validator · specialists · fewshot · registry · scope |
| `engine/recipes/` | `triage · content · refine · review` |
| `usecases/` | the interactive step-by-step explorers embedded in the site (triage · content · refine) |
| `engine/mcp/` | MCP client + server (optional extra) |
| `engine/live/` | the browser view + the synthetic care-intake case (optional extra) |
| `examples/` · `evals/` · `tests/` | real runs & runnable demos · grading harness · tests |
| `state/examples/` | the gold examples (few-shot + eval), one folder per domain — sources + licenses in [`DATA-NOTICE.md`](DATA-NOTICE.md) |
| `tools/` | public-data harvesters, per-domain eval, generality check, explorer builder |
| `docs/` | [`SPEC`](docs/SPEC.md) · [`execution-walkthrough`](docs/execution-walkthrough.md) (one run, line by line) · [`control-flow`](docs/control-flow.md) · [`learning-loop`](docs/learning-loop.md) · [`standards`](docs/standards.md) · [`mcp`](docs/mcp.md) · [`provenance/`](docs/provenance/) · [`RESULTS`](docs/RESULTS.md) · [`depth`](docs/depth.md) (the hard parts, honestly) · [`blind-evals`](docs/blind-evals.md) (results on blind test sets) |

Full CLI: `run · approve · compose · board · view · replay · eval · fit · benchmark · train · review · capture · examples · registry · costs`.

## Cost

Text costs **$0 per call** in development — the brain is Claude via the CLI on a Max plan. `engine/core/brain.py` is a
swappable port; the Anthropic-API backend (`ENGINE_BRAIN=api`) is there for a deployment that needs
it. No paid LLM in the loop by default.

## License

Code: [MIT](LICENSE). The gold-example data in `state/examples/` keeps its sources' licenses —
see [`DATA-NOTICE.md`](DATA-NOTICE.md) (the Wikipedia / Stack Exchange files are CC BY-SA 4.0).
