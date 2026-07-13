# Engine — Glossary

The single source of truth for Engine's vocabulary. Define each term once, here; other docs link to this.

## The actors — who does things

- **Composer** *(a.k.a. orchestrator)* — builds a **new** recipe from the library for a use case; drafts
  specialists for gaps.
- **Validator** — checks a recipe-graph is well-formed (entry/exit/reachability, loop termination, dangling
  outputs, references, contracts) before it runs. Static; no execution.
- **Dispatcher** — runs an **existing** recipe: fires each specialist the moment its inputs are ready, owns
  all board writes, handles gates. Deliberately dumb — it only follows the recipe.
- **Specialist** — an agent that does one capability. Three flavors:
  - **Capability-specialist** — generic, reused everywhere: the five — `fetch · classify · rank · verify · act`.
  - **Domain-specialist** — bespoke to one domain (`route`, `respond`, `write`, `review`, …).
  - **Provisional specialist** — a *drafted*, untrusted one (no eval yet), awaiting validation via the gate.

## What flows, and where

- **Recipe** — the plan for one use case: today a linear chain of steps; soon a graph of steps + edges.
- **Step** — one node in a recipe: a specialist + its config + its input wiring + maybe a gate.
- **Edge** — a connection between steps; conditional (branch), backward (loop), or a join (fan-in). A step's
  `join` (`and`/`or`) decides how multiple in-edges combine.
- **Board** — the durable shared state everything coordinates through (crash-safe).
- **Hopper** — the intake: where work-items enter the board.
- **Work-item** — one thing flowing through a recipe (an issue, a topic, a PR).
- **Card** — one tracked unit of work (a work-item at a step). Status: `todo · ready · running · gated · done ·
  failed`.
- **Gate** — a human sign-off pause between cards.

## The parts shelf

- **Library** *(registry)* — the catalog of specialists, with metadata + track-records.
- **Contract** — a specialist's fixed input/output shape (the "plug") — what makes specialists interchangeable.
- **Adapter / shim** — a thin transform that reshapes input to fit a contract (absorb variation without
  forking a specialist).
- **Brain** *(port)* — the swappable Claude call behind judgment specialists (CLI free / API billed).

## The record

- **Trace** — the run log: every state transition (the raw material for the future visualization).
- **Track-record** — a specialist's accumulated run count + latest eval score, in the registry.
- **Eval** — the accuracy/validity check *every* specialist must ship with (the blueprint convention).

## The learning loop *(see `learning-loop.md`)*

- **Exemplar** — a curated `{input, output}` pair a specialist learns from (few-shot), in
  `state/examples/<scope>/<specialist>.jsonl`. Human-approved; the model instance to imitate.
- **Batch** — a set of exemplars generated for review in one pass of the trainer.
- **The trainer** *(`engine train`)* — the local review app that generates a batch, surfaces the hard calls,
  and lets a human approve/improve/skip into exemplars. (Renamed from "the tester" — "test" is reserved for
  automated code tests.)
- **Coverage-aware generation** — *composing* inputs to span the space (categories, urgency bands, planted
  failures) instead of sampling — because a narrow batch teaches nothing.
- **Devil's advocate** — a confidence-gated adversarial second opinion (argue the other side, or concede)
  that surfaces genuinely contestable exemplars.
- **Planted failure** — a deliberately-corrupted input used to train a checker (`verify`) — it must see
  failures to learn to catch them, and the corruption must be *unambiguously* wrong.
- **Universal vs. customer layer** — the skill (role + model) generalizes and ships once; the examples are
  task-specific. Universal specialists are dropped in untouched; customization is domain modules + config.
- **Baseline training** — the universal floor: examples shared across every deployment (e.g. RESPOND's
  composite "good reply" craft). Trained once, reused.
- **Tailored training** — a customer's own examples layered on top of the baseline (their voice / edge
  cases). Called *tailored*, not "specialized," to avoid colliding with **specialist** (the agent).
- **Baseline if reusable; tailor always** — a new specialist gets a universal *baseline* only if it's
  genuinely reusable (then it joins the shared shelf); a bespoke one is *born tailored* (general-skill
  floor + that customer's examples, living in their deployment). Tailoring always happens; baseline is
  conditional. Drives the compounding curve — new-specialist work is front-loaded and decays per customer.
- **Retrieval, not drawers** — one example memory; inject the few most *similar* to the current call. The
  general skill is always the floor (examples are upside-only when relevant).

## Disambiguation — overloaded words, one meaning each

These words were carrying 2–4 meanings and causing stumbles. Canonical rules:

- **test** → *only* automated code tests (`tests/`, run by `run_all.py`). NOT quality checks, NOT the
  review app, NOT a validation demo.
- **eval** → a specialist's quality/accuracy check (the blueprint convention). Not a "test".
- **the trainer** → the `engine train` review app (was "the tester").
- **proof / demo** → a script validating a mechanism end-to-end (lives in `examples/`).
- **output** vs **exemplar** → a specialist emits an **output** (its raw answer for one input, not yet
  trusted). It becomes an **exemplar** only once a human approves/corrects it in the trainer/gate. The
  trainer *produces exemplars by curating outputs*; exemplars (baseline for general use, tailored per use
  case) then make future outputs better. "example" the bare word is avoided (collides with the `examples/`
  dir); the older term "gold" is retired in favor of "exemplar".
- **item** (a.k.a. **work-item**) → the thing flowing through a recipe (issue / PR / topic). The entries in a
  training **batch** are *exemplars*, never "items".
- **card** → a work-item at one step (item × step). The board is a grid of cards.
- **use case** (the job) vs **customer** (who has it) vs **recipe** (the plan that does it) vs **deployment**
  (a running instance for one customer) vs **scope/tenant** (that customer's data-isolation namespace). The
  chain: *a customer has a use case, realized by a recipe, running in a deployment, isolated by a scope.*
  Portfolio demo scenarios are **showcases** (to distinguish from real customers).

## One cross-cutting concept

- **Altitude** — board-level (the *operation*: work waits/recurs) vs. pipeline-level (one *item*: work flows).
  The board wraps pipelines.
