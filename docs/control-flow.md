# Engine — Control Flow

> Status: **BUILT (Phase 14, 2026-07-09).** Recipes are `steps + edges`; the dispatcher is edge-driven
> (branches, loops, joins); a static Validator checks graphs before they run; the Composer draws the edges
> and repairs against the Validator. This note is the spec for the shipped behavior. Companion to `DESIGN.md`.

## The principle

Don't hardcode `foreach`, `while`, `branch` as separate features. Provide **one general representation** — a
graph of steps connected by **edges** that can be conditional and can point backward — and let every pattern
(branch, while-until, foreach, recursive-expansion, draft-critique-revise, fan-out-then-synthesize) fall out
as a *shape* in that graph. One tiny mechanism; unlimited patterns.

**Compose-time dynamism, not runtime free-for-all.** The **Composer** decides the loops/branches and emits an
*inspectable* control-flow graph; the **dispatcher** executes that graph. The graph is dynamic (it wrote
itself, per use case) but, once written, it is inspectable, gate-able, and validatable. We deliberately do NOT
let the orchestrator decide arbitrary control flow *at runtime* — that is just a general think-act-observe
agent, and it dissolves the structure (specialists, contracts, board, gates, evals) that makes Engine worth
more than raw Claude. The knife-edge: **dynamic where it counts, structured where it protects you.**

## Representation

A recipe goes from a list to **steps + edges**:

```
Recipe:
  steps: [ { id, specialist, config, inputs }, … ]           # unchanged from today
  edges: [ { from, to, when? }, … ]                          # NEW
  guard: { max_visits_per_step: 5 }                          # NEW — so backward edges terminate

Edge:
  from: <step id>            # leaves the END of this card
  to:   <step id>            # arrives at the BEGINNING of this card (may be an EARLIER step -> loop)
  when: <condition expr>?    # optional; default = always. A boolean over a prior step's output,
                             #   e.g. "classify.label == 'spam'"  or  "critique.satisfied == false"
  join: "and" | "or"?        # on the TARGET card, when it has multiple in-edges (default: and)
```

A **linear** recipe is the special case: one unconditional edge from each step to the next. Today's recipes
are exactly this, so nothing breaks.

## The three primitives (everything is built from these)

Edges do three things, depending on where they attach and where they point:

1. **Split** — multiple edges *out of* a card's end, each with a `when`. The dispatcher follows whichever
   condition holds → a **branch**.
2. **Join** — multiple edges *into* a card's beginning. `join: "or"` = run on the first to arrive (branches
   reconverging); `join: "and"` = wait for all (fan-**in** / synchronize).
3. **Loop** — an edge whose `to` is an *earlier* step, guarded by `max_visits_per_step` so it terminates.

`when` conditions ride on the edge — which is simultaneously "the end of the source card" and "the start of
the target card."

## Patterns as shapes

**Linear** (today):
```
classify ──▶ rank ──▶ verify ──▶ act
```

**Branch** (split — conditional out-edges):
```
                ┌─(when label == "spam")──▶ discard
classify ──▶ ───┤
                └─(when label != "spam")──▶ respond ──▶ act
```

**While / until — draft-critique-revise** (loop — a backward edge):
```
draft ──▶ critique ──┬─(when NOT satisfied)──▶ draft   ⟲   (guard: ≤ 4 passes)
                     └─(when satisfied)──────▶ act
```

**Fan-out → synthesize** (AND-join — the multi-reviewer pattern):
```
        ┌──▶ security_check ──┐
review ─┼──▶ style_check ─────┼──(join: and)──▶ synthesize
        └──▶ test_check ──────┘
```

**Recursive expansion** (backward edge that spawns new work-items into the hopper):
```
research ──▶ find_subquestions ──(for each, when depth < 2)──▶ [new research item] ⟲
```
Fits the hopper naturally — a step emits new work-items; some of *those* emit more; the depth guard stops it.

**Foreach** (honest nuance): iterating a step over a *known list within one item* maps more naturally onto the
**hopper** (spawn one work-item per element) than onto a control-flow loop. Treat data-parallel iteration as a
hopper concern; reserve edges for control flow.

## What changes in the code

**Dispatcher** — one rule changes. Today: "next = next step in the list." New: *when a card finishes, look at
its out-edges, evaluate each `when` against the output, and promote the matching target(s)."* A target card
becomes ready per its `join`: `and` = all in-edges satisfied, `or` = any. Backward edges are followed the same
way; the `max_visits_per_step` guard blocks infinite loops. The board, pull-based loop, pipelined concurrency,
and "dispatcher owns writes" are all **unchanged** — only "what's next" moves from hardcoded to edge-driven.

**Composer** — emits `steps + edges` instead of a bare list. "Determining the loops/branches" *is* drawing the
edges: a backward edge for a loop, two conditional edges for a branch, an AND-join for fan-in.

**Conditions** — a small boolean expression language over step outputs (`step.field == value`,
`> < != and or`), evaluated the same way inputs are already resolved (`step.field` references exist today).

## The edges ARE the program — entry/exit included, and a validator checks them

The dispatcher is deliberately dumb: it only follows edges. So *all* correctness lives in how well the edges
are drawn at compose time. Two consequences:

**Entry and exit are edges too — nothing special-cased.** Today intake is CLI code that seeds the hopper
*outside* the graph, and a dangling `verify` verdict is a *missing* outgoing edge. Both are the same smell:
flow that isn't expressed as an edge. In the graph model the *whole* flow is edges — a defined **entry** (where
work-items arrive; `fetch` can be the entry node that emits items), every conditional branch, joins, and a
reached **exit**. Nothing lives outside the graph.

**A compose-time graph validator (a "compiler" for the composed graph).** The Composer *draws* the edges; a
validator *checks them before the dispatcher runs them*. It catches:
- **dangling outputs** — a step whose result influences nothing (that's `verify` today);
- **unreachable steps**, **no defined entry**, **exit never reached**;
- **unguarded loops** (no termination condition/guard), **malformed joins**;
- **forward / typo references** (caught at compose time, earlier than the dispatcher's runtime guard).

This is what makes compose-time dynamism *trustworthy* and lets the dispatcher stay simple: it executes only
*validated* edges. Three clean roles — **Composer draws → validator checks → dispatcher executes** — and the
validator is exactly where the "Composer reliability is the central risk" gets mitigated.

## Honest costs / risks

- **Composer reliability is the central risk.** Emitting *valid* control flow — loops that terminate,
  conditions that are correct, joins that make sense — is a much bigger ask than emitting a linear list. We
  already watched the Composer fumble config-vs-inputs. Expressiveness trades directly against Composer
  reliability, so the eval + provisional-until-validated discipline matters *more* here, not less.
- **Termination must be guaranteed** — the visit-guard/budget is not optional.
- **Keep it inspectable.** The whole point is a graph you can read, gate, and validate before it runs. If a
  design pressure pushes toward "decide at runtime," that's the signal we're drifting toward a general agent —
  stop and reconsider.

## The Composer is NOT limited in what it can express

The whole point of one general mechanism is that the Composer can draw **any** control-flow shape — it must
never tell the user "I can't do that kind of loop." It is not choosing from a fixed menu of loop types; it is
arranging primitives (conditional edges, backward edges, joins) into whatever the described workflow needs. The
two constraints below are a **safety net** and an **inspectability choice**, NOT limits on expressiveness:

- **Compose-time decides the graph, not runtime.** The Composer draws the graph once, so it stays inspectable
  and gate-able. This does *not* reduce what can be expressed: `when` conditions are evaluated at **runtime**,
  so "loop until satisfied" works without knowing the count ahead of time; and even *agentic* behavior is
  expressible — a while-loop around a "decide the next action" specialist. A **step** may decide at runtime;
  what we don't do is let the orchestrator rewrite the graph mid-run (that's a generic agent, and it dissolves
  the structure — specialists, contracts, gates, evals — that makes Engine worth more than raw Claude).
- **Loops carry a termination guard.** A backstop so a loop can't run forever — which the user never wants
  anyway. "Loop until done" is the *condition*; the guard just prevents a runaway.
