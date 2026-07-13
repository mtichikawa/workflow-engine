# Engine Core Spec — primitives, contracts, and the two recipes

> The paper foundation before Phase 1 code. Everything snaps onto these. Companion to `DESIGN.md`.

## 1. Primitives

### Specialist
A unit that performs one capability. Two kinds: **capability** (generic, reused) and **domain** (bespoke).
Some specialists are pure code (adapters, `fetch`); judgment specialists call the **brain port** (Claude).

**Blueprint rule (enforced):** every specialist ships with an eval in `evals/suite.py` — an *accuracy* eval
(labeled right answers) for judgment specialists, a *validity/smoke* check for generative/mechanical ones.
`engine eval` runs them all and flags any specialist without one. **A specialist without an eval is incomplete.**

```
Specialist:
  name:     str
  kind:     "capability" | "domain" | "adapter"
  contract: Contract
  run(input: dict, config: dict) -> dict     # output MUST satisfy contract.output
```

### Contract
The fixed input/output shape — the "plug." Anything honoring it is interchangeable.

```
Contract:
  input:  dict schema   # required keys + types
  output: dict schema   # guaranteed keys + types
```

### Recipe
An ordered chain of steps. Each step names a specialist, its config, where its input comes from, its
dependencies, and whether a gate follows it.

```
Recipe:
  name:  str
  steps: [ Step ]

Step:
  id:        str
  specialist: str            # name in the library
  config:     dict           # categories/criteria/scoring/etc. — authored here, NOT by the dispatcher
  input_from: str | dict     # a prior step id, or a mapping/adapter expression
  depends_on: [str]          # step ids that must be `done` first
  gate:       bool           # if true, pause for human approval AFTER this step
```

### Board — the "hopper" (persistent, multi-item)
Durable state (JSON under `state/`). You feed work-items in (the hopper); the board holds MANY items in flight
at once, each flowing through the recipe's steps. Crash-safe: the dispatcher reconciles from it.

```
Board (persistent):
  recipe: str
  items:  { item_id: { payload: dict, status } }   # fed into the hopper (batch or over time)
  cards:  [ Card ]                                   # one per (item, step) currently live

Card:
  item_id: str                # which work-item this card belongs to
  step_id: str                # which recipe step
  status:  "todo" | "ready" | "running" | "blocked" | "gated" | "done" | "failed"
  input:   dict | null
  output:  dict | null        # the specialist's return, satisfying its contract
  attempts:[ {ts, error?} ]
```
**Model A** (one issue at a time) is just this board with a *single* item. **Model B** (the live kanban board)
is *many* items at once — same structure, same dispatcher. Build the multi-item model from the start; validate
on one item; batch-load ~20 for the live-board demo.

### Dispatcher
Runs a recipe against the board. Pull-based, mechanical — makes **no** domain decisions, and **owns all board
writes** (specialists are pure `input -> output`, so parallel runs never clobber shared state).

```
loop until the board is drained (no pending items, all live cards done/failed):
  intake:  new items in the hopper -> seed their first card as `todo`
  promote: any todo card whose depends_on are all `done` -> ready
  run:     take ALL `ready` cards -> run each specialist(input, config)
             - fan-out: a step over a list produces one child card per element (1A)
             - sequential now; concurrency = run ready cards in parallel under a cap (LATER, no refactor)
           collect returns -> DISPATCHER writes outputs to the board -> mark done
             - if step.gate -> mark `gated`, stop that branch until human approve()
  gated cards wait for `engine approve <item> <step>` -> then their dependents promote
```
Concurrency is free-by-design (ephemeral, stateless specialists): flip it on later by running the ready cards
in parallel under a cap. Not in the first pass — the design just never precludes it.

### Gate
A `gated` card halts its branch until a human runs `engine approve <run_id> <step_id>` (or edits the board).
Used at judgment/irreversible points (before `act`, before publish).

### Adapter
A thin, usually pure-code specialist (`kind="adapter"`) that reshapes one step's output into the next
specialist's `input` contract. Absorbs input variation so capability-specialists are never forked. Keep thin.

### Brain port (swappable)
Judgment specialists call `brain(prompt, ...)`. Two adapters: **CLI** (`claude -p`, free on Max — dev/proof)
and **API** (`anthropic`, billed — product). Config flag selects; recipes never care which.

## 1b. Locked decisions (pre-build cycle, 2026-07-09)

**Design (baked into the primitives above):**
- **Hopper / Model B from the start** — multi-item board; feed work in, it sorts and flows items through the
  stages. Validate on ONE item, then batch-load ~20 for the live-board demo. (1B)
- **Fan-out** — a step maps over a list / over items, one child card each. Robust for all cardinalities. (1A)
- **Concurrency-ready, built later** — dispatcher owns writes, specialists are pure fns, cap knob; flip on by
  running ready cards in parallel. No refactor. (concurrency)
- **Genuinely-shared specialists** — the five capability-specialists are ONE instance each, imported by both
  recipes (a shared skeleton); "shared" must not drift into a fiction. (1C/2B)

**Cross-cutting (build in from day one):**
- **Logs / run trace** — dispatcher emits every state transition; near-free (the board records everything).
  This is also the minimal presentation layer. (2A/2C)
- **Tiny eval per capability-specialist** — 5–10 labeled cases each, to confront early whether the specialists
  are actually good (the thing everything rests on). (2A/5A)
- **Low temperature** on judgment specialists (classify/verify); accept residual non-determinism. (4C)
- **Gate captures corrections as examples** — when the human corrects an output at a gate, save
  `{input, corrected output}` as a labeled example (Mike corrects, for now). (3C)

**Deliverable added:**
- **Presentation layer** — the live kanban-board view / a 60-second demo. Minimal = the logs; fancy = an HTML
  board later. (4A)

**Deferred (NOT in the two-recipe proof):**
- The **Composer** + **library-registry** — spec'd AFTER the two recipes are built + validated. (3A)
- A **third recipe**, built fast, to demonstrate compounding. (3B)
- **Live-streaming intake** (webhooks) — batch-load for now. **Failure/retry policy** — at scaling. (4B)
- A **full generation middle** (e.g. a real voice/cut/render backend behind a content specialist).
- Name **"engine"** collides with an existing company — fine as a working name; decide before any product brand. (1D)

## 2. The five shared capability-specialist contracts

```
fetch     IN  { source, params }
          OUT { items: [ dict ] }              # 1..n structured records

classify  IN  { item, categories: [str], criteria: str }
          OUT { label: str, confidence: 0..1, reasoning: str }

rank      IN  { items: [dict], scoring: str }
          OUT { ranked: [ { item, score: 0..1, reasoning } ] }   # desc by score

verify    IN  { subject, standard: str }       # a claim OR a prior decision
          OUT { verdict: "pass"|"fail", confidence: 0..1, issues: [str] }

act       IN  { target, payload, mode: "staged"|"live" }
          OUT { status: "staged"|"sent"|"skipped", result: dict }
```

Every one is **config-driven**: same implementation, different `categories`/`criteria`/`scoring`/`standard`.

## 3. The two recipes wired

### Recipe A — Triage (greenfield; built first)
```
1 fetch     config{ source:"github", params:{repo, since} }            -> items(issues)
2 classify  config{ categories:[bug,feature,question,duplicate,spam],
                    criteria:"issue type" }   input_from:1(each item)   -> label
3 rank      config{ scoring:"urgency: blocking>affects-many>nice" }     -> ranked
4 route     (domain) config{ components:[...] }                          -> label(component)
5 respond   (domain) config{ tone, templates }                          -> draft_reply
6 verify    config{ standard:"classification+route match the issue" }    -> verdict
7 act  GATE config{ target:"github", mode:"staged" }                     -> staged labels+comment
```

### Recipe B — Content, light (built second; proves REUSE)
```
1 fetch     config{ source:"web", params:{topic/query} }               -> items(sources)
2 classify  config{ categories:[angle types], criteria:"resonance" }    -> label
3 rank      config{ scoring:"resonance/relevance" }                      -> ranked
4 write     (domain) config{ format:"post", brief }                      -> draft_post
5 verify    config{ standard:"claims supported; on-brand; FTC-safe" }    -> verdict
6 act  GATE config{ target:"file|social", mode:"staged" }               -> staged post
```

Shared, identical implementations across both: `fetch · classify · rank · verify · act` (steps 1,2,3 + verify
+ act). Domain-only: triage's `route`,`respond`; content's `write`. **That overlap is the proof.**

## 4. Build order (Phase 1 → 4)
1. `core/`: Specialist, Contract, Recipe, Board, Dispatcher, Gate, brain port → hello-world recipe runs.
2. `specialists/`: the five capability-specialists, each contract-tested in isolation.
3. Recipe A (triage) on a real public repo, staged/gated.
4. Recipe B (content, light) reusing the five → both run on one core.
