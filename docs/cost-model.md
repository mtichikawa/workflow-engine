# Cost model & reduction plan

Text is free during dev (the CLI brain on a Max plan bills $0). This doc is about the
**ship path** — what the same work costs on the billed API — so we can reason about it
before we switch. Every brain call is now metered (`state/token_log.jsonl`, `engine costs`).

## The measured number

One `classify` call (2026-07-10): **~3,174 input + 54 output tokens ≈ $0.01** at Sonnet
list price ($3 / $15 per 1M in/out). Cost is dominated by **input** — output was tiny.

Scaling that naively: **100 items × 5 steps = 500 calls ≈ $5–7** (generative steps like
`write`/`respond` emit more output, which is 5× the price of input). That's real money at
volume (100k items = thousands of dollars) — and it's the **ceiling**, not the floor.

## Where the cost is

Most of those 3,174 input tokens are **identical across every item** through a given
specialist: the system prompt, the rubric, the instructions. We're re-paying for the same
boilerplate on every call. That redundancy is the fat to cut.

## The levers (ranked; none built yet — the API brain is held)

1. **Prompt caching** — the static system+rubric is the same for all items through a
   specialist; Anthropic caches it at ~10% after the first call. For a batch of N through
   one specialist the cache stays hot → roughly **halves** input cost. Biggest win for this
   exact shape.
2. **Per-specialist model tier** — Haiku ($0.80/$4) is ~4× cheaper than Sonnet. The simple
   judgments (`classify`, `rank`, `route`, `verify`) run fine on Haiku; reserve Sonnet for
   `write`/`respond`. The model is already a per-call knob, so this is a small change.
3. **Branches already cut it** — the control-flow graph doesn't run every step on every
   item. Spam is classified once and dropped (downstream `skipped`); the verify-gate stops
   `act` on failures. Real batches make *fewer* than 500 calls.
4. **Trim the input** — `classify`/`rank` mostly need the title + first paragraph, not the
   full body (env dumps, stack traces). Trim per step (carefully — `verify` needs detail).
5. **Cascade** — run Haiku first, escalate to Sonnet only when uncertain (the same
   disagreement signal the trainer uses; and the pattern Mike already built into microclaw:
   stronger model for complex calls / as a fallback on failure).

Stack caching + Haiku-for-simple + branches and the realistic number is **~$1–2 per 100
items**, plausibly less — 2–4× below the ceiling, with mostly-easy changes.

## Stance

- **Dev is $0** (CLI/Max). This is pre-measurement for the ship path, not a current bill.
- **Per item ≈ $0.05** to run five AI judgments — cheap against a human doing the same
  triage. The concern is *volume* and *margin*, which is why we measure now and tune before
  scaling.
- When we build the API brain, wire in **per-specialist model routing + prompt caching**
  first; the metering already in place is what makes it tunable.
