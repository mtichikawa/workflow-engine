# Depth — the hard parts, built from scratch (and what's actually proven)

On paper this engine reads as LangGraph + DSPy + Snorkel + LLM-judge recombined. The defense is the
hard parts built by hand, and an honest account of what the evidence supports. This doc makes
that legible so the depth is visible, not asserted.

## The parts built from scratch (non-trivial, defensible)

**1. Static control-flow validator** (`core/validator.py`)
Recipes are `steps + edges` (branches/loops/joins). Before a run, a static checker verifies the
graph: entry/exit, reachability, **loop termination** (a backward edge must have a guard),
dangling outputs, condition references, contract compatibility. This is a little type-checker for
the recipe graph — invalid graphs are rejected *before* execution, not discovered mid-run. The
Composer repairs against it in a compile-error loop.

**2. Provisional → trusted promotion** (`registry.py`, `evals/`)
A drafted specialist starts *provisional* (untrusted, exempt from the eval convention). It earns
**trust** only when its eval clears a bar (≥0.8 on ≥4 examples). The convention (`eval`)
enforces "every *trusted* specialist ships with an eval." This is a real trust lifecycle, not a
flag — draft → validate → track-record → promote.

**3. Per-tenant scope seam** (`scope.py`, `examples.py`)
The multi-tenant data-model seam, built before it was needed (retrofitting it is the expensive,
leak-prone part). Isolation **by path** (`state/examples/<scope>/…` — you can't read another
tenant without naming their dir, no filter to forget) + **ambient scope via `contextvars`** set
once at entry (specialists never see it). **Building it surfaced a real bug:** `ThreadPoolExecutor`
doesn't propagate `contextvars` to worker threads, so few-shot in a threaded specialist silently
ignored `--scope` — i.e. the tenant seam broke under `concurrency > 1`. Found + fixed
(`copy_context()` at submit). A bug scan then found a second one of the same class (an unlocked
concurrent append in the cost meter). This is the kind of depth that only shows up when you build
the runtime yourself.

**4. Pipelined edge-driven dispatcher** (`core/dispatcher.py`)
Deliberately dumb: it owns every board write, specialists are pure, and "what runs next" is driven
entirely by the recipe's edges. Each work-item flows independently (no barrier) — a fast item
races ahead while a straggler is still on an earlier stage. Concurrency is safe *by construction*
(pure specialists + single writer), not by locking everything.

**5. The learning loop** (`fewshot.py`, `trainer.py`)
Retrieval-injected few-shot with a per-scope baseline+tailored layering, content-only similarity
(a fix found by testing — config fields were confounding retrieval), and coverage telemetry that
flags when a run falls back to baseline (active-learning signal). And an empirical finding it
produced: few-shot helps "mapper" specialists but *hurts* the checker (verify: 9/10 without vs
8/10 with) — which became a general rule (adopt an enhancement per-specialist only if its eval
improves).

## The Composer — honest stress-test (tested 2026-07-11, because this claim is the thinnest)

Ran `compose()` on 5 use cases spanning coverable → gap → novel:

| use case | composed | outcome |
|---|---|---|
| screen support emails | classify → rank → respond → verify → act | **runnable** ✓ |
| triage bug reports | classify → rank → route → act | **runnable** ✓ |
| moderate comments | classify → rank → *moderate* → verify → act | flagged gap `moderate`, **not runnable** (honest) |
| review legal contract | reused review/verify/rank/classify + *segment_clauses* | flagged gap, **not runnable** (honest) |
| medical lab report | *extract* → *flag_ranges* → *summary* → verify | flagged **3** gaps, **not runnable** (honest) |

**What's genuinely proven (defensible, verifiable):**
- Decomposes a plain-English use case into a specialist pipeline and wires a **valid** graph.
- **Reuses** library specialists correctly (compounding).
- **Honestly flags gaps and refuses to claim runnable** when specialists are missing — it does not
  hallucinate capability. 2/2 coverable → runnable; 3/3 gap cases → correctly non-runnable.

**What's thinner (soft-pedal, per the portfolio review):**
- *"Writes its own specialists."* The draft path exists (validated earlier on a legal-clause gap)
  and produces a real instruction+contract stub — but a drafted specialist is *provisional* and
  needs human validation before it's trustworthy. Frame as "drafts provisional stubs for gaps,"
  never "autonomously writes working specialists."
- **Non-deterministic.** Same use case composes differently across runs (moderation was a `moderate`
  gap one run, reused `classify` the next). Both defensible, but disclose it — a skeptic will see it.
- Minor rough edge: occasional step-id vs specialist-name mismatch in the composed output.

## The Composer writes AND tests its own specialists — the benchmark (2026-07-11)

The "writes specialists" claim was thin, so we made it **verifiable and non-circular** (Mike's
idea): have the Composer re-derive specialists we ALREADY have — classify/rank/route — from a
plain-English *description* (not the original's code), then score each against that specialist's
**real, human-labeled eval**. Independent ground truth; the auto-written version competes against
the hand-built one on the same test. (`autotest.py`, reproducible via `benchmark`.)

```
                auto-written        hand-built
  classify      6/6  (100%)         6/6
  rank          3/3  (100%)         3/3
  route         3/3  (100%)         3/3
  (all: 0 crashes, non-degenerate, contract-compliant)
```

From a task description alone, the Composer wrote specialists that **matched the hand-built
originals on independent, human-labeled evals.** That's real evidence it writes *working*
specialists, not plausible stubs.

**Self-test + self-repair** (`write_and_test`): a written specialist runs a structural suite —
contract compliance, no-crash on diverse inputs, non-degeneracy — and the instruction is
auto-repaired (bounded) if it fails. Demonstrated on a fresh `moderate` specialist (passed first
try; coherent output).

**Honest caveats (attached to the claim):**
- Evals are small (6/3/3 cases) — a coarse filter; "matches" = clears the same bar, on few cases.
- Determinism (consistency at temp 0) is NOT testable on the free CLI brain — `claude -p` ignores
  temperature, so every call varies; the scores are single-pass. Reproducible on the API brain.
- These are WELL-SPECIFIED tasks. Domain CORRECTNESS of a genuinely novel specialist is
  self-generated and still requires the **human gate** — the `moderate` demo kept "you are all
  idiots" as non-toxic (coherent, but a debatable call a human must own).

**Honest verdict:** lead the portfolio with the **learning loop** (cleanest evidence), and now the
Composer has real teeth too: *"given a description it writes a specialist that matches my
hand-built one on the same human-labeled eval (100% on all three tried), self-tests it
structurally, and self-repairs — with domain trust still gated by a human."* Verifiable
(`benchmark`), non-circular, and honest about its limits.
