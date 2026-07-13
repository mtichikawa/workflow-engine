# Engine — Visualization

> Status: **BUILT (Phase 15, 2026-07-09).** `engine replay <run_id>` emits a self-contained, scrubbable HTML
> replay of a run. Reads the board's recorded event log; no server. The full form of the presentation layer
> (logs → the `engine view` grid → this animated replay). Companion to `control-flow.md`.
>
> **Superseded in practice by the interactive explorer + gallery (below, 2026-07-13).** The replay animates
> *one run's timeline*; the explorer renders *the recipe as a node-editor graph* with the real run's values
> inline and click-to-expand detail. The explorer is what the portfolio leads with.

## The interactive explorer + gallery (BUILT, 2026-07-13)

A Blender/ComfyUI-style **node-editor explorer**, one per use case, **generated from `(recipe + real run log)`
with no per-recipe hand-curation**. Plus a **gallery** (accordion of use cases) whose cards each show a live
mini of that recipe's graph. Both are self-contained HTML (no server, no CDN).

### The pieces
- **`engine/graph_core.js`** — the shared layout + orthogonal router, a pure `makeGraphCore(NODES, WIRES, cfg)`
  factory (no DOM, no `window`). Owns: self-layout (columns = dataflow depth, each centered on one axis),
  socket positions, the **parametric orthogonal router** (`route(i, geom)` — channel lanes, over/under
  highways for multi-column spans, loops up-and-over, fork/join junctions), topology coloring
  (split=teal, merge=violet, loop=coral, gate=amber), and `roundedPath`. **Inlined into both consumers at
  build time**, so each stays self-contained and there is exactly one router — no drift.
- **`engine/explorer_engine.html`** — the full explorer: render + interaction (hover-highlight, click-to-expand
  with reflow, truncate+expand for long outputs) layered on the core. Placeholders `__GRAPH_CORE__ /
  __NODES__ / __WIRES__ / __TITLE__ / __DESC__`.
- **`engine/explorer.py`** — the generator. `BLURBS` (the *only* hand-written text: one display template per
  specialist, reused everywhere), `build_graph` (structure from the recipe — kinds, columns, sockets, data +
  gate + loop wires), `generate_cards` / `build_data` (values + the specialist's own reasoning **verbatim**
  from the run log; per-pass trail for looped steps), `build_html` (inject into the engine template).
- **`tools/build_explorer.py`** — CLI: `python tools/build_explorer.py <slug>` → `usecases/<slug>/index.html`.
  Run logs live in `usecases/_runs/` (committed) so generation is reproducible from a clean clone.
- **`tools/build_gallery.py`** — the gallery (`usecases/index.html`) from `usecases/usecases.json`. Each card's
  mini is the **same core** fed the recipe graph, rendered small (card silhouettes + dots flowing along the
  real `route()` paths), scaled by viewBox. Uses the explorer's exact proportions so the wires are identical.
- **Portfolio teaser** — `mtichikawa.github.io/index.html` `#mbsvg` inlines the same core + the triage graph,
  stripped to card silhouettes + flowing dots, fit into a fixed box. One router, three surfaces.

### Load-bearing detail
- **No per-recipe curation.** Structure comes from the recipe, values+reasoning verbatim from the run log,
  and ~8 per-specialist blurbs written once. New recipes reuse the blurbs as-is; new specialists need one
  blurb. The explorer *is generated* — it reproduced the hand-built one and auto-shows new fail paths / loops.
- **Loop history is universal.** The dispatcher appends each pass's output to `card.attempts`; any step with
  >1 attempt renders its pass-by-pass trail via its own blurb (no per-recipe code). Proven on a real looping
  refine run (draft→fail→fail→pass).
- **Router bug fixed (5c67eb3).** `route()` short-circuited to a straight line whenever source and dest sockets
  shared a y — even for a spanning wire whose decision was a *highway* (because the direct line is blocked),
  plowing straight through the intermediate card. Latent in the explorer (misaligned sockets rarely trigger
  it), constant in the mini (single-card columns all center on one axis). Guarded with `dec.t!=='hwy'`.
  Verified by a headless wire-vs-card intersection check across all three graphs → clean.

## The vision

Not a flowchart. A flowchart is dead — it shows the *shape*. This shows the **machine thinking**: an
**animated replay** of an execution, where you watch work flow through the recipe.

- The recipe rendered as a **graph** (nodes = specialist-steps, edges = the control flow).
- Work-items flow through as **glowing tokens** — entering the hopper, gliding along edges to each node.
- A node **pulses** as its specialist fires.
- **Parallel tokens move at once** — the pipelined fan-out, made visible.
- A token **loops back** on a loop-edge; tokens **split** at a branch; tokens **merge** at an AND-join.
- A node glows **amber** = a gate waiting for a human.
- **Hover a node** to see the actual output it produced (from the board).

## Replay, not live — deliberately

The whole thing runs in *seconds*, so a live stream would be an unwatchable blur. A **replay is better**: it's
scrubbable, pausable, and speed-controllable — you slow it down to actually *see* the parallelism and the
flow, or scrub to a moment and inspect. **You control the pace.** (Live-streaming would also need a running
server; replay is a static page.)

## Why it's achievable — the data already exists

This is **not new instrumentation** — it's *rendering data we already capture*:
- The **board** (`state/<run>.json`) persists every card's `status`, `input`, and `output`.
- The **trace** (`logs/<run>.log`) logs every state transition — and cards carry timings via attempts.

So a visualization = **replay the board + trace**. The hard part (knowing what happened, and when) is done.
(One small future add: stamp each card commit with a timestamp in the board so the replay timeline is exact.)

## The synergy: the control-flow graph IS what you visualize

Once recipes are `steps + edges` (see `control-flow.md`), the recipe *is* a graph — so the viz is "draw the
graph, animate tokens along the edges." The execution model and the visual are the **same object**: loops loop
on screen, branches split, joins merge. The two design notes reinforce each other.

## Technical approach

- **Self-contained HTML page**, no server. Loads a run's board + trace (embedded or fetched local file) and
  animates the replay. Shareable — can be published as an Artifact.
- **Canvas or WebGL** for smooth token motion (not hand-authored SVG paths); a laid-out or force-directed
  graph. Respect `prefers-reduced-motion`.
- A **timeline scrubber** with play / pause / speed. The board+trace give the event sequence; the renderer
  interpolates token positions along edges between events.
- Start with the **replay-a-single-run** version (fastest route to the "oh" moment); a multi-run / live tier
  can come later if ever wanted.

## Honest scope

The data and model are ready; what remains is real front-end craft — graph layout + smooth animation + the
scrubber. Bounded, but not trivial. It is genuinely **differentiating** (most agent projects have zero
visualization), and it's the natural payoff of the board+trace instrumentation already in place.

## Status

Designed, not built. Build the replay version when the visual payoff is wanted (strong portfolio moment).
