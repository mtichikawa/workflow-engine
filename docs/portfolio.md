# Modular Multi-Agent Workflow Automation
### An architecture for coordinating specialized AI agents through a composable task-graph — demonstrated on content production, but domain-agnostic by design.

> **Caveat up front (load-bearing):** the instance below automates content production, but that is *one instantiation*. The architecture is a general pattern for automating any multi-step, judgment-heavy workflow — the kind of work that was considered "human-only" until recently. Swap the specialist agents and the composition, and the same skeleton automates claims adjudication, document review, compliance checks, or support triage. **The content specifics are adapters; the pattern is the product.**

## Part 1 — The general pattern (domain-agnostic)

**The shape:** an *overseer* (coordinator) orchestrating a team of *modular specialist agents*, each doing one narrow task, coordinating through a *durable task-graph board*, with *human gates* at points of judgment or irreversibility, composed into per-use-case *recipes*.

**The core components:**
- **Overseer / dispatcher** — a single coordinator loop that reads a shared board, promotes work whose dependencies are met, and spawns the right specialist for each ready task.
- **Specialist agents** — each is one concept doing three jobs at once: a *unit of work* (does one task), a *unit of learning* (carries its own persistent memory and improves over time), and a *unit of composition* (a swappable brick). Spun up per task, load their role + memory, do the job, write results back, disappear.
- **Task-graph board** — durable shared state (status columns: todo → running → done; cards linked by dependencies). Agents coordinate *only* through this board, never by messaging each other.
- **Human gates** — wait-states at judgment calls and irreversible actions (approve, publish). The human stays the judgment layer where it matters; everything mechanical flows automatically.
- **Recipes** — a use case is just an *ordered chain of specialist-cards*. Configure a new use case by choosing which capabilities are present and which specialist fills each slot.

**The design decisions that make it work (and demonstrate the reasoning):**
- **Steal the coordination *design*, not a runtime dependency.** The pattern is implemented on lightweight, native primitives rather than adopting a heavyweight external agent platform — keeping control, cost, and portability.
- **The altitude rule — board vs. pipeline.** Work that *waits* (on a human, another agent, or across time) or *recurs* (monitoring) belongs on the board. Work that *flows* start-to-finish in one pass is a plain pipeline. The board *wraps* pipelines: it dispatches a ready item, the pipeline runs, it reports back. This prevents over-engineering (not every step needs coordination machinery).
- **Fine granularity = modularity.** One specialist per real *capability* (not per keystroke, not one giant monolith). This *is* what makes the system modular — you reconfigure per use case by swapping bricks. Bricks come in dependency clusters, so composition respects the dependency structure.
- **Pull-based polling over durable state, not event-driven push.** The overseer reconciles a durable board on a tick. Crash-safe, no missed-event bugs, trivially cheap — deliberately chosen over a more "elegant" event bus.
- **Two kinds of memory.** *Factual* memory (what's been done) is safe to accumulate immediately; *judgment* memory (what works) is only trustworthy once a real validation signal exists — otherwise agents confidently learn noise.
- **The honest boundary: the value is not the graph.** The orchestration engine is a commodity (it's the Power Automate / Zapier / LangGraph shape, and every major lab ships one). The durable value lives in the *specialists' domain judgment*, *system integration*, and *earned trust* — the parts specific to the work being automated. The architecture is designed so effort concentrates there.

## Part 2 — The content-production instance (concrete)

The same skeleton, with content-specific specialists:

- **Specialists:** trend-research · script · voice · cut/assemble · output-format · publish. Each narrow, each accumulating its own lane memory.
- **"The machine does everything but the recording."** A human records real, tagged footage of a real product doing real things (the one thing a machine can't authentically produce); the system writes the script, generates voiceover, matches tagged clips to script beats, cuts them *to the voiceover* (using word-level timing), captions, assembles, and publishes.
- **Two altitudes, concretely:** an *operation board* manages the backlog, the footage library a human fills over time, and videos *blocked* on clips that aren't shot yet; each ready item drops into a *production pipeline* that runs start-to-finish.
- **Recipes show the modularity:**
  - `microclaw video` = trend → script → seed → **shoot (human)** → cut → publish
  - `generic video` = trend → script → stock-footage → voice → cut → publish
  - `LinkedIn-only` = trend → script → format → publish *(drops the entire audio/visual cluster)*
- **The human's only irreplaceable jobs:** supply genuine reality (record) and judge at the gates. Everything else is specialist work.
- **One input → every format:** a single idea fans out to video, article, LinkedIn post, and thread.

## Part 3 — Why it generalizes (the caveat, expanded)

Everything in Part 1 is written without a single content-specific word — because content is incidental. To retarget the architecture at a different domain, you change only two things:

1. **The specialists** — replace "script / voice / cut" with the domain's capabilities ("intake / classify / adjudicate / verify" for claims; "extract / cross-reference / flag / summarize" for document review).
2. **The recipes** — chain those specialists to match the target process, keeping human gates at the high-stakes and irreversible steps.

The overseer, the board, the altitude rule, the granularity-as-modularity principle, the pull-based coordination, the two-memory model, and the human-gate design are **all unchanged.** That invariance *is* the portfolio claim: this isn't a content tool that happens to be reusable — it's a general workflow-automation architecture with content as its first proof.

And the honest framing that signals maturity: the hard part of automating formerly "human-only" work is never the orchestration (that's scaffolding) — it's making each specialist's *judgment* trustworthy enough to remove the human, verifying it, and handling the tail. This architecture is deliberately shaped so the human stays gated at exactly those points, and so effort concentrates on domain judgment rather than on rebuilding a commodity graph.
