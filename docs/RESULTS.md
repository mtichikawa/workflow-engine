# Engine — build results (step-2 proof)

Built end-to-end in one session: the core engine, five shared capability-specialists,
two unrelated recipes, and the proof that they run on one core sharing the same
specialists. All validated on **real data with real (free, CLI) Claude calls.**

## What runs

```
python -m engine.cli run triage  --repo vercel/next.js --limit 5     # real GitHub issues
python -m engine.cli approve <run_id>                                 # approve the staged actions
python -m engine.cli run content --topic "…" --brief "…" --auto       # a light content post
python -m engine.cli view <run_id>                                    # HTML board view
python tests/proof_shared.py                                         # the reuse proof
python -m engine.cli eval                                             # every specialist, + convention check
```

## The proof (two domains, one core, five shared specialists)

```
Triage domain middle : route, respond
Content domain middle: write
Shared by BOTH recipes: classify, rank, verify, act  (+ fetch via triage intake)
Each is a single shared instance — reuse is structural, not convention.
```

Both recipes are the same skeleton; only the middle differs:
`fetch → classify → rank → [ domain middle ] → verify → act`.

## Real output — triage (vercel/next.js, staged, gated, nothing posted)

Three live issues went through the hopper in parallel. Example staged result:

- issue #95637 → **classified** `bug` (0.98), **ranked** `0.85` ("production outage"),
  **routed** `core`, **verified** `pass`, and a **drafted reply** that asks for exactly
  the missing specifics (`next info`, the full server-side stack trace, the Turbopack vs
  webpack matrix, the `output: 'standalone'` config) — a genuinely useful first response,
  staged as labels `[bug, core]` + comment, awaiting human approval.

## Real output — content (topic → post, reusing the five)

Topic: *"Why most AI agent demos fall apart in production"* → staged post:

> Most demos run one happy path against a cached prompt. Production hits you with a 3%
> tool-timeout rate, retries that double your token bill, and a 12-step chain where each
> step at 95% reliability compounds to 54% end to end. The demo never showed you the error
> handling because there wasn't any.

On-brand (no hype, numbers over adjectives); `verify` flagged one number to double-check.

## Specialist quality (the thing everything rests on) — Phase 9

`python -m engine.cli eval` runs an eval for **every** specialist and enforces the blueprint rule that a
specialist without an eval is incomplete. Latest run — all passing:

```
classify  accuracy  6/6 100%     act     smoke  1/1
rank      accuracy  3/3 100%     fetch   smoke  1/1
route     accuracy  3/3 100%     respond smoke  1/1
verify    accuracy  3/3 100%     review  smoke  1/1
                                 write   smoke  1/1
  ✓ every registered specialist has an eval.
```

Judgment specialists get accuracy evals (labeled right answers); generative/mechanical ones get
validity/smoke checks. The architecture rests on the specialists being good — and on this evidence they are.

## Step 3 — compounding + the Composer

**Third recipe (code review), built fast.** `fetch(PRs) → classify → rank → review → verify → act`.
Only **one new specialist** (`review`) and one `fetch` source — everything else reused. Validated on 2
real open PRs (astral-sh/ruff): correctly ranked a core type-checker change `0.7` vs an isolated lint
rule `0.15`, produced findings + a staged review comment. Recipe #3 cost a fraction of recipes #1–2 —
that drop in marginal cost is the compounding, shown live.

**The Composer — a recipe that writes recipes.** Given a plain-English use case + the specialist catalog,
it decomposes, selects library specialists, assembles a runnable recipe, and flags gaps.

- *Coverable use case* — "Screen a support message: categorize, gauge urgency, draft a reply, check it":
  the Composer assembled `classify → rank → respond → verify → act` (reusing 4 of 5 + respond from triage)
  and **ran it untouched** — categorized `billing`, urgency `0.98`, drafted a reply, verified, staged.
- *Gap case* — "Review a legal contract and flag risky clauses": the Composer reused verify/rank/act,
  **flagged a needed new specialist** `flag_clauses` with a proposed contract (`[item, focus] →
  [findings, clause_count, summary]`) and an honest reason, and reported *not runnable as-is* — it refused
  to pretend a specialist it doesn't have exists.

```
python -m engine.cli run review --repo astral-sh/ruff --limit 2 --auto
python -m engine.cli compose "screen a support message…" --run --input "…" --auto
python -m engine.cli compose "review a legal contract…"          # flags the gap
```

## Concurrency (Phase 7)

Ready cards fan out in parallel (thread pool + cap). Safe by design — the dispatcher owns every board
write and specialists are pure `input → output`, so parallel workers never clobber shared state.

**Benchmark: 5 items, 2.02s sequential → 0.42s parallel (~4.8× faster), with identical board writes.**

**Pipelined dispatch (Phase 12):** each item flows *independently* — no barrier between stages. The instant a
card finishes, its next is dispatched, so fast items race ahead while a straggler is still on an earlier stage.
`tests/test_pipelining.py` proves it: a fast item cleared *both* stages 0.70s before a slow item finished
stage 1 — impossible under a wave/barrier model.

```
python -m engine.cli run triage --repo vercel/next.js --limit 8 --concurrency 4
```

## Tests (Phase 8)

`python tests/run_all.py` — **13 core unit tests + a timed concurrency test, all passing**, deterministic and
brain-free: contract validation (pass / missing / wrong-type), board save-load round-trip, input resolution
(payload / step / composite / literal), gate + approve, failure blocks downstream, multi-item flow, brain-JSON
parsing, registry. Plus `tests/proof_shared.py` (the reuse proof) and `evals/` (specialist accuracy).

## Gate-as-example-factory (Phase 11)

Your corrections at the gate become labeled training data. `engine review <run_id>` writes an editable JSON of
each gated item's specialist outputs; you fix any you disagree with; `engine capture <run_id>` saves every
`{input, output}` to `state/examples/<specialist>.jsonl` and approves the gates. Validated end-to-end: a
gated content run produced **4 labeled examples** (classify/rank/verify/write; mechanical fetch/act skipped).
The registry (`engine registry`) tracks each specialist's run count + latest eval — examples + track-records
are the fuel for the learning loop (you're the corrector for now).

## Control flow (Phase 14)

Recipes are `steps + edges` — one general mechanism for branches, loops, and joins (linear recipes
auto-linearize, so everything prior is unchanged):
- **branches** — conditional out-edges; an untaken branch leaves its cards `skipped`;
- **loops** — a backward edge with a `when`, bounded by a visit guard, keeping the source's output as feedback;
- **joins** — multiple in-edges, `and` (wait for all) or `or` (first).

**The concrete win:** `verify` now *gates* `act` — `verify → act when verify.verdict == 'pass'` — across all
three recipes. Verification failing means the action is skipped, not blindly taken. (`rank`/`classify` outputs
also flow into the staged result, so every step's output is consumed and the recipes validate clean.)

**The Validator** (`engine`'s static graph checker) verifies entry/exit/reachability, loop termination,
dangling outputs, references, and contracts *before* a run — the CLI blocks invalid graphs. The **Composer**
draws the edges from plain English and repairs against the Validator (a compile-error loop).

Verified live: the Composer composed *"screen a support message; if spam, stop; otherwise draft, verify,
stage only if it passes"* into a real **branch + verify-gate**; a spam input → screen labeled it spam →
`draft`, `vet`, `stage` all **skipped** (correctly dropped). Fully unit-tested: branch · OR-join · AND-join ·
loop-converge · loop-guard + validator cases.

## Visualization (Phase 15)

`engine replay <run_id>` writes a **self-contained, scrubbable HTML replay** of a run: the recipe graph with
work-items as colored tokens that flow through it as you scrub a timeline, nodes flashing as each step
completes, branches/loops/gates drawn, hover a node for the outputs there. It replays the board's recorded
event log — no server (a run takes seconds, so you control the pace). The full form of the presentation layer:
logs → the `engine view` grid → this animated replay.

## The learning loop — training the specialists (Phase 16)

`engine train <specialist>` — a local review app to build a specialist's example set. Spec:
`learning-loop.md`. Generation is **coverage-aware** (composes inputs to span the space) and
**surfaces only the hard calls** via a confidence-gated devil's advocate, so curation barely
needs the human. Proven across three genuinely different shapes:

```
python -m engine.cli train classify --generate 12   # multi-repo pool + spam/question/edge seeds
python -m engine.cli train rank                      # urgency + high-urgency RCE/outage/data-loss seeds
python -m engine.cli train verify                    # real subjects + PLANTED failures (a checker needs them)
python -m engine.cli costs                           # every brain call metered -> estimated API cost
```

Baselines built for the three **shared judgment specialists** — the reusable core in every recipe:

```
classify  5 exemplars   bug · feature · question · spam (4 categories, was 90%-bug)
rank      5 exemplars   1.00 (security RCE) → 0.50 → 0.35 → 0.15 → 0.00 (spam)  — a real gradient
verify    4 exemplars   2 pass (clean triage) + 2 fail (caught a wrong label, a generic reply)
```

Honest findings the trainer surfaced: real issues are mostly unambiguous (challenging found ~zero
genuine disagreements — the lever is insurance, not a work source); manufactured failures must be
*unambiguously* wrong (a mis-route planted on spam, where routing is moot, produced a false "miss").
`act`/`fetch` are mechanical (smoke tests, no examples); `route`/`respond`/`write` are domain
specialists, trained per recipe.

**Back half — the loop closed (Phase 17).** A specialist now retrieves its curated exemplars by similarity
and injects the relevant few (`fewshot.py`); a provisional specialist earns trust by eval
(`registry.promote`). Proven end-to-end (`examples/learning_loop_demo.py`):

```
weak drafted specialist, policy ORTHOGONAL to severity (escalate on churn signal, not anger)
  COLD (no examples, follows severity prior)        4/8  = 50%
  WARM (6 curated exemplars injected as few-shot)       8/8  = 100%   (+50%, independent eval set)
  provisional -> promoted to TRUSTED (eval >= 0.8 on >= 4 examples)
```

A specialist measurably learning, from human corrections, a rule it could not have guessed.

**Domain specialists (Phase 18).** `route` (classify-shaped) is wired into the trainer the same way —
baseline of 5 across core/build/docs/other; routing's fuzzy boundaries (build vs core) were the first
inputs to actually trip the disagreement lever. `respond`/`write` are generative, so the trainer gained a
generative path + a **prose-editing mode** (edit the reply/post as plain text with a live preview, not raw
JSON). Voice baselines are the user's to curate — voice is the one thing the human genuinely can't delegate.

Six specialists now train through one tester: classify · rank · verify · route (curated baselines) +
respond · write (generative, ready for voice curation).

## What's deferred (by design)

The Composer + library-registry (step 3), a third recipe, live-streaming intake,
concurrency (the design is concurrency-ready — dispatcher owns writes, specialists are
pure — it's a flip, not a refactor), a failure/retry policy, and the full video middle.
