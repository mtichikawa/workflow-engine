# How the engine runs a workflow — a from-scratch, line-by-line walkthrough

This document assumes you know **nothing** about how the engine executes, and builds up to a complete
trace of one real workflow. We'll use one concrete example — the `refine` recipe (draft → check →
loop-until-good → publish) — and follow a single piece of work all the way through: the recipe, the
dispatcher, one specialist in full, the edges, the loop, and the gate.

By the end you should be able to answer: *what is a recipe, what is the dispatcher, how does the
dispatcher decide what runs next, how does it know a step finished, how does data get from one step to
the next, and how does a loop work.*

---

## 0. The four nouns (the whole mental model)

Everything in the engine is one of four things. Keep these straight and the rest follows.

| Noun | What it is | In one line | File |
|---|---|---|---|
| **Recipe** | the *program* — a graph of steps and edges | *what to do, and in what order* | `core/recipe.py` |
| **Specialist** | a *function* the program calls | *does one thing (classify, write, verify…)* | `specialists/*.py` |
| **Board** | the *memory* — durable, on disk | *the state of every piece of work* | `core/board.py` |
| **Dispatcher** | the *interpreter/CPU* | *walks the graph and runs the steps* | `core/dispatcher.py` |

The single most important idea: **the Dispatcher is generic and dumb.** It is the same code for every
workflow. It makes *no* decisions about *what* to do — all of that lives in the Recipe (the graph) and
the Specialists (the reasoning). The Dispatcher only follows edges and moves work between statuses. That
separation is why one small, well-tested engine can run any workflow.

Analogy: the Recipe is a program, the Dispatcher is the interpreter that runs any program, the
Specialists are the functions the program calls, the Board is the program's memory.

---

## 1. The example: the `refine` recipe

Here is the actual file, `engine/recipes/refine.py`, in full:

```python
from engine.core import Edge, Recipe, Step

REFINE = Recipe(name="refine", max_visits=4, steps=[
    Step(id="write", specialist="write", domain=True,
         inputs={"topic": "payload.topic", "sources": "payload.sources", "brief": "payload.brief",
                 "feedback": "verify.issues"}),        # None on first pass; verify's issues on a loop

    Step(id="verify", specialist="verify",
         inputs={"subject": {"draft": "write.post", "topic": "payload.topic"}},
         config={"standard": "STRICT — fail unless ALL hold: contains AT LEAST TWO distinct "
                            "concrete numeric statistics ...; names a specific failure mode; "
                            "uses NO hype words ...; no emojis; under 4 sentences. ..."}),

    Step(id="act", specialist="act", gate=True,
         inputs={"payload": {"content": "write.post", "name": "payload.slug"}},
         config={"target": "file", "mode": "staged"}),
], edges=[
    Edge("write", "verify"),
    Edge("verify", "write", "verify.verdict == 'fail'"),   # LOOP: revise until it passes (guarded)
    Edge("verify", "act", "verify.verdict == 'pass'"),     # then publish (gated)
])
```

### 1.1 What this says, drawn as a graph

Three **steps** (the boxes) connected by three **edges** (the arrows):

```
                 ┌──────────────────────────────────────┐
                 │   (loop back if the check FAILS)      │
                 ▼                                       │
   payload → [ write ] ──────► [ verify ] ──fail?────────┘
             (draft a           (check it            
              post)              vs a strict          
                                 standard)            
                                     │
                                     └──pass?──► [ act ] (GATE) ──► staged file
                                                 (publish,
                                                  needs human OK)
```

- **write** drafts a post.
- **verify** checks that draft against a strict quality standard and returns `pass` or `fail`.
- If **fail**, the edge `verify → write` loops back so `write` can revise (it's given verify's
  complaints as feedback). This repeats until it passes, but no more than `max_visits=4` times.
- If **pass**, the edge `verify → act` moves forward to publish.
- **act** has `gate=True`, meaning it **stages** the result and **waits for a human to approve** before
  the run is considered finished.

### 1.2 Every field on a `Step`, explained

A step is defined by this dataclass (`core/recipe.py`). *(A Python "dataclass" is just a class where you
list the fields and Python writes the boilerplate `__init__` for you — `Step(id="write", ...)` fills
these in.)*

```python
@dataclass
class Step:
    id: str                              # a name unique within the recipe, e.g. "write"
    specialist: str                      # which specialist to run, e.g. "write"
    config: dict = field(default_factory=dict)   # STATIC values you choose now
    inputs: dict = field(default_factory=dict)   # LIVE data, pulled from payload or earlier steps
    gate: bool = False                   # if True, pause for human approval after this step
    domain: bool = False                 # cosmetic: is this a bespoke domain step vs a shared capability
    join: str = "and"                    # if a step has several in-edges: "and"=wait for all, "or"=first
```

The crucial distinction is **`config` vs `inputs`**:

- **`config`** = *static* values decided when the recipe is written/composed and never change at runtime.
  Example: verify's `standard` (the quality bar) and act's `target: "file"`. These are constants.
- **`inputs`** = *live* values pulled from data that only exists at runtime — the incoming work item, or
  the output of an earlier step. These are written as little **source expressions** (strings):

  | expression | means |
  |---|---|
  | `"payload"` | the whole incoming work item |
  | `"payload.topic"` | the `topic` field of the incoming item |
  | `"write.post"` | the `post` field of the `write` step's output |
  | `"verify.issues"` | the `issues` field of the `verify` step's output |
  | anything else (e.g. `"result.txt"`) | a literal string |

  So `write`'s `inputs={"topic": "payload.topic", ...}` means "when you run `write`, set its `topic`
  argument to the incoming item's `topic` field." This is the **wiring** between steps.

Note `write`'s input `"feedback": "verify.issues"`. On the **first** pass, `verify` hasn't run yet, so
this resolves to `None` (no feedback). On a **loop** pass, `verify` *has* run and produced `issues`, so
`write` receives them and revises. That single wire is what makes the loop meaningful.

### 1.3 Every field on an `Edge`, explained

```python
@dataclass
class Edge:
    src: str                 # step id the arrow leaves
    dst: str                 # step id the arrow enters
    when: str | None = None  # a condition on src's output; None = always follow this edge
```

Three edges in `refine`:

- `Edge("write", "verify")` — unconditional (`when=None`): after `write`, always go to `verify`.
- `Edge("verify", "write", "verify.verdict == 'fail'")` — only follow if verify's verdict was `fail`.
- `Edge("verify", "act", "verify.verdict == 'pass'")` — only follow if verify's verdict was `pass`.

A **branch** is simply two edges out of one step with different `when` conditions (that's exactly the two
edges leaving `verify`). A **loop** is an edge that points *backward* — to a step that appears *earlier*
in the `steps` list. `verify → write` is backward because `write` (position 0) comes before `verify`
(position 1). The engine figures this out itself:

```python
def _order(self, step_id):        # position of a step in the steps list
    return self.step_ids().index(step_id)

def is_backward(self, e):         # an edge is a loop if it points at or before its source
    return self._order(e.dst) <= self._order(e.src)
```

### 1.4 The graph queries the Dispatcher will use

The Recipe exposes a few helper methods. You don't need to memorize them, just know they answer simple
graph questions. `forward_in` and `backward_out` are the two that matter most:

```python
def in_edges(self, step_id):      # all edges pointing INTO this step
    return [e for e in self.edges if e.dst == step_id]

def out_edges(self, step_id):     # all edges leaving this step
    return [e for e in self.edges if e.src == step_id]

def forward_in(self, step_id):    # in-edges that are NOT loops → what must finish before this can start
    return [e for e in self.in_edges(step_id) if not self.is_backward(e)]

def backward_out(self, step_id):  # out-edges that ARE loops → where to jump back to when this finishes
    return [e for e in self.out_edges(step_id) if self.is_backward(e)]

def loop_body(self, dst, src):    # the steps to RESET when a loop fires: dst .. src inclusive
    lo, hi = self._order(dst), self._order(src)
    return self.step_ids()[lo:hi + 1]
```

For `refine`:
- `forward_in("write")` = `[]` — the only edge into `write` is the backward loop, which doesn't count as
  a prerequisite. So `write` is an **entry step** (nothing needs to finish before it).
- `forward_in("verify")` = `[Edge("write","verify")]` — `verify` waits for `write`.
- `forward_in("act")` = `[Edge("verify","act", pass)]` — `act` waits for `verify` (and only if it passed).
- `backward_out("verify")` = `[Edge("verify","write", fail)]` — when `verify` finishes, this is the loop
  it might fire.
- `loop_body("write", "verify")` = `["write", "verify"]` — if that loop fires, reset both `write` and
  `verify` to re-run.

---

## 2. The Board: where the state lives

The Board is the durable memory. It holds many work-items at once; each item flows through the recipe.
The unit of state is a **Card**: one (item, step) pair, with a status.

```python
STATUSES = ("todo", "ready", "running", "blocked", "gated", "skipped", "done", "failed")

@dataclass
class Card:
    item_id: str
    step_id: str
    status: str = "todo"        # where this (item, step) is in its lifecycle
    input: dict | None = None   # the resolved arguments handed to the specialist
    output: dict | None = None  # what the specialist returned
    attempts: list = field(default_factory=list)  # history (a loop appends each pass)
    visits: int = 0             # how many times this step has run for this item (the loop counter)
    coverage: dict | None = None  # telemetry: few-shot layer split (ignore for now)
```

The statuses are the lifecycle of a card:

- **todo** — exists, not yet eligible to run.
- **ready** — all prerequisites satisfied; eligible to run.
- **running** — handed to a worker thread; the specialist is executing.
- **done** — finished successfully.
- **skipped** — a branch that was not taken (e.g. the `fail` path when it actually passed).
- **gated** — finished, but waiting for human approval (a gate).
- **failed** — the specialist raised an error.
- (`blocked` exists in the enum but isn't used by this path.)

The Board also holds **`context`**: for each item, a dict of `{step_id: that step's output}`. This is the
data the wiring reads from.

```python
def record_output(self, item_id, step_id, output):
    self.context.setdefault(item_id, {})[step_id] = output   # e.g. context["item"]["write"] = {"post": ...}
```

Two Board facts to note:
- **It's crash-safe.** `save()` writes to a temp file then atomically renames it over the real one, so a
  crash never leaves a half-written file. Every dispatcher iteration calls `save()`.
- **It's the resume point.** If a run pauses at a gate, `Board.load(run_id)` reconstructs the whole state
  from disk; a fresh Dispatcher picks up exactly where it left off. The Dispatcher itself holds no
  durable state — the Board does.

---

## 3. The Specialist: one function, with a contract

Every specialist inherits from this base (`core/specialist.py`). The base `run()` is a wrapper; each
specialist implements `_run()`.

```python
class Specialist:
    name = "unnamed"
    contract = Contract(input={}, output={})   # declares the required input/output shape

    def run(self, input, config=None):
        config = config or {}
        merged = {**config, **input}            # combine the static config + the live inputs
        self.contract.validate_input(merged)    # fail loudly if a required field is missing
        output = self._run(merged, config)       # the actual work (may call the brain)
        self.contract.validate_output(output)    # fail loudly if the wrong shape came back
        return output
```

Two things this guarantees:
1. **A specialist can never silently return the wrong shape.** The contract check means `verify` always
   returns `{verdict, confidence, issues}` or it errors — so downstream steps and edge conditions can
   rely on it.
2. **`config` and `inputs` arrive merged.** Inside `_run`, both the static config (`standard`) and the
   live inputs (`subject`) are available as one dict.

Specialists are registered as **shared singletons**:

```python
_REGISTRY = {}
def register(spec):  _REGISTRY[spec.name] = spec; return spec
def get(name):       return _REGISTRY[name]          # dispatcher calls this to find the specialist
```

`get("verify")` returns the one shared `Verify` instance. Because specialists are **pure** (they read
their inputs, return output, and touch no shared state), one shared instance can safely run on many
threads at once.

---

## 4. Two Python concepts you'll need (explained from scratch)

The Dispatcher uses two standard-library tools. Here's just enough to read the code.

### 4.1 Threads, a thread pool, and Futures

- A **thread** is a second line of execution in the same program, running "at the same time" as the main
  one. Useful here because a specialist spends almost all its time *waiting* on the `claude` subprocess;
  while it waits, other specialists can run.
- A **`ThreadPoolExecutor(max_workers=N)`** is a manager that keeps N worker threads ready and hands them
  work.
- **`pool.submit(fn, a, b)`** says "run `fn(a, b)` on a worker thread." It does **not** wait for the
  result — it immediately returns a **`Future`**.
- A **`Future`** is a placeholder object for a result that doesn't exist yet — a claim ticket. Later,
  when `fn` finishes, the pool stores its return value inside the Future and marks it "done." You read
  the value with `future.result()` (which also re-raises the exception if `fn` crashed).
- **`wait(futures, return_when=FIRST_COMPLETED)`** puts the *calling* thread to sleep until **at least
  one** of those Futures is done, then returns the set of finished ones. This is how the Dispatcher waits
  efficiently — it isn't polling ("are you done? are you done?"); it's *asleep* until the pool wakes it.

**This is the answer to "how does the dispatcher know a specialist is done":** the specialist is an
ordinary function on a worker thread; when it *returns*, the pool sets that thread's Future to "done" and
signals the sleeping `wait()`, which wakes the Dispatcher. No polling, no callbacks, no messages — just a
function returning, in the same process, waking a parked thread.

### 4.2 `contextvars` (why the worker thread needs a copy of the context)

The engine has an "ambient scope" (set once by `--scope acme`) that tells specialists which tenant's few-shot
examples to use. It's stored in a **`contextvars.ContextVar`** — a variable whose value is *per-execution-
context*. The catch: a new worker thread does **not** automatically inherit it. So before dispatching,
the Dispatcher snapshots the current context and runs the specialist *inside* that snapshot:

```python
ctx = contextvars.copy_context()               # snapshot the ambient scope (and any contextvar)
pool.submit(ctx.run, self._execute, card, step)  # run the specialist inside that snapshot
```

Without this, a threaded specialist would ignore `--scope` and always read baseline examples. You can
mostly ignore this detail — just know that's what those two lines are for.

---

## 5. The Dispatcher, method by method

Now the engine itself, `core/dispatcher.py`. We'll go through each method, then trace a real run.

### 5.1 Construction

```python
class Dispatcher:
    def __init__(self, recipe, board, tracer, concurrency=1):
        self.recipe = recipe          # the graph
        self.board = board            # the state
        self.trace = tracer           # writes events for `engine replay`
        self.concurrency = concurrency  # how many specialists may run at once
```

It holds references, nothing more. A Dispatcher is cheap and disposable — you make one, call `run()`, and
throw it away. (On resume, you make a fresh one from the loaded Board.)

### 5.2 `run()` — the main loop

This is the heart. Read the comments:

```python
def run(self, auto_approve=False):
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    self.trace.event("run", f"recipe={self.recipe.name}", items=len(self.board.items), mode="pipelined")
    self._intake()                                  # (1) give every (item, step) a card

    with ThreadPoolExecutor(max_workers=max(1, self.concurrency)) as pool:
        inflight = {}                               # Future -> (card, step) currently running
        self._submit_ready(pool, inflight)          # (2) dispatch whatever is ready right now

        while inflight:                             # (3) as long as something is running…
            done, _ = wait(set(inflight), return_when=FIRST_COMPLETED)   # sleep until one finishes
            for fut in done:
                card, step = inflight.pop(fut)       # remove it from the in-flight set
                try:
                    self._commit(card, step, fut.result())   # (4) record its output, fire loops/gates
                except Exception as e:
                    self._fail(card, step, str(e))            # a crash becomes a "failed" card
            self._submit_ready(pool, inflight)       # (5) dispatch anything newly unblocked
            self.board.save()                        # (6) checkpoint to disk

            if not inflight:                         # (7) nothing running…
                gated = self.board.with_status("gated")
                if gated and auto_approve:           # …if only gates remain and we're auto-approving,
                    for c in gated:
                        self.approve(c.item_id, c.step_id, auto=True)  # approve them
                    self._submit_ready(pool, inflight)                 # and continue past the gate

    self._finalize()                                 # (8) mark any unreachable cards skipped
    self.board.save()
    kind = "pause" if self.board.with_status("gated") else "done"
    self.trace.event(kind, "waiting on gates" if kind == "pause" else "board drained",
                     snapshot=self.board.snapshot())
    return self.board
```

The shape of the loop: **dispatch everything ready → sleep until one thing finishes → commit it →
dispatch whatever that unblocked → repeat.** When nothing is left running, either we auto-approve
remaining gates and keep going, or we stop. If gated cards remain and we're *not* auto-approving, the
`while inflight` condition is false, the loop exits, and the run **pauses** — to be resumed later.

Notice there is no per-step scheduling logic here. "What runs next" is entirely computed by
`_submit_ready` → `_readiness` from the graph's edges. The loop is generic.

### 5.3 `_intake()` — lay down the cards

```python
def _intake(self):
    for item_id in self.board.items:
        if not self.board.cards_for(item_id):
            for s in self.recipe.steps:
                self.board.add_card(item_id, s.id, "todo")   # every step gets a "todo" card
```

For each work-item, create one `todo` card per step. For our single item and 3 steps, that's 3 cards:
`(item, write)=todo`, `(item, verify)=todo`, `(item, act)=todo`.

### 5.4 `_promote()` / `_readiness()` — the brain of scheduling

This is where the graph decides what may run. `_promote` walks every `todo` card and asks `_readiness`
whether it should become `ready` (runnable) or `skipped` (a branch not taken).

```python
def _promote(self):
    for card in self.board.with_status("todo"):
        status = self._readiness(card.item_id, card.step_id)
        if status:
            card.status = status
            if status == "skipped":
                self.board.log_event(card.item_id, card.step_id, "skipped")

def _readiness(self, item_id, step_id):
    fin = self.recipe.forward_in(step_id)     # the non-loop edges that must be satisfied
    if not fin:
        return "ready"                        # no prerequisites → entry step → runnable now

    results = []                              # for each in-edge: (did the source finish?, was its condition true?)
    for e in fin:
        src = self.board.card(item_id, e.src)
        src_status = src.status if src else "todo"
        resolved  = src_status in ("done", "skipped", "failed")   # the source has reached a terminal state
        satisfied = src_status == "done" and self._cond(e.when, item_id)  # …and its condition holds
        results.append((resolved, satisfied))

    join = self.recipe.step(step_id).join
    if join == "or":
        if any(sat for _, sat in results):        return "ready"    # any one satisfied → go
        if all(res for res, _ in results):        return "skipped"  # all resolved, none taken → skip
    else:                                          # "and"
        if all(sat for _, sat in results):        return "ready"    # every prerequisite satisfied → go
        if any(res and not sat for res, sat in results):  return "skipped"  # a required edge came back false → skip
    return None                                    # still waiting on a source → stay todo
```

In words, for the default `and` join:
- **ready** when *every* forward in-edge is satisfied (source `done` **and** its `when` condition true).
- **skipped** when some required in-edge has *resolved false* — the source finished but its condition was
  false, so this step can never run (that's how the un-taken branch of `verify` gets cleaned up).
- **None** (stay `todo`) when we're still waiting for a source to finish.

This is the *entire* scheduling policy. It's pure bookkeeping over the graph — no LLM, deterministic.

### 5.5 `_submit_ready()` — resolve inputs and dispatch

```python
def _submit_ready(self, pool, inflight):
    import contextvars
    self._promote()                                  # first, update statuses
    slots = self.concurrency - len(inflight)         # how many more we may start
    for card in self.board.with_status("ready"):
        if slots <= 0:
            break
        step = self.recipe.step(card.step_id)
        try:
            card.input = self._resolve_input(step, card.item_id)   # turn the wiring into real values
        except Exception as e:
            self._fail(card, step, f"input resolution: {e}")
            continue
        card.status = "running"
        ctx = contextvars.copy_context()             # carry the ambient scope into the thread
        inflight[pool.submit(ctx.run, self._execute, card, step)] = (card, step)
        slots -= 1
```

For each `ready` card, up to the concurrency limit: **resolve its inputs** (next section), mark it
`running`, and **submit it** to the thread pool. The returned Future is stored in `inflight` so the main
loop can match a finished Future back to its card.

The worker just calls the specialist:

```python
@staticmethod
def _execute(card, step):
    return registry.get(step.specialist).run(card.input, step.config)
```

### 5.6 `_resolve_input()` — how data flows between steps

This turns the wiring strings (`"payload.topic"`, `"write.post"`) into actual values.

```python
def _resolve_input(self, step, item_id):
    return {field: self._resolve_expr(expr, item_id) for field, expr in step.inputs.items()}

def _resolve_expr(self, expr, item_id):            # inputs can nest dicts/lists of expressions
    if isinstance(expr, dict):  return {k: self._resolve_expr(v, item_id) for k, v in expr.items()}
    if isinstance(expr, list):  return [self._resolve_expr(e, item_id) for e in expr]
    return self._resolve(expr, item_id)

def _resolve(self, expr, item_id):
    head, _, tail = expr.partition(".")            # "write.post" -> head="write", tail="post"
    ctx = self.board.context.get(item_id, {})      # {step_id: that step's output}
    if head == "payload":
        base = self.board.items[item_id]["payload"]   # the incoming work item
    elif head in ctx:
        base = ctx[head]                              # a prior step's output
    elif any(s.id == head for s in self.recipe.steps):
        return None                                   # a real step that hasn't produced output yet
    else:
        return expr                                   # not a reference → a literal string
    if base is None or not tail:
        return base
    for key in tail.split("."):                       # walk the dotted path into the dict
        if not isinstance(base, dict):  return None
        base = base.get(key)
    return base
```

Three cases, which cover everything:
1. `"payload.xyz"` → reach into the incoming item's payload.
2. `"stepid.field"` where `stepid` already ran → reach into that step's saved output in `context`.
3. `"stepid.field"` where `stepid` **hasn't** produced output yet → `None`. **This is exactly what makes
   `write`'s `feedback: "verify.issues"` safely `None` on the first pass** and real on a loop pass.
4. anything that isn't a payload/step reference → treated as a literal (e.g. a filename `"result.txt"`).

### 5.7 `_commit()` — record output, then gate or loop

When a specialist finishes, this runs:

```python
def _commit(self, card, step, output):
    card.output = output
    card.attempts.append({"output": output})       # per-pass history (loops accumulate)
    card.visits += 1                                # bump this step's run counter
    card.coverage = self._coverage(step, card.input)  # telemetry only
    self.board.record_output(card.item_id, step.id, output)  # put it in context for downstream wiring

    if step.gate:                                   # a gated step STOPS here, waiting for a human
        card.status = "gated"
        self.board.log_event(card.item_id, step.id, "gated")
        self.trace.event("GATE", f"{card.item_id}:{step.id}", out=output)
        return

    card.status = "done"
    self.board.log_event(card.item_id, step.id, "done")
    self.trace.event(step.id, card.item_id, out=output)
    self._fire_loops(card.item_id, step.id)         # maybe jump back and re-run
```

Two branches: if the step is a **gate**, mark it `gated` and stop (the run will pause for approval). Else
mark it `done` and check whether any **backward (loop) edge** should fire.

### 5.8 `_fire_loops()` — the loop mechanism

```python
def _fire_loops(self, item_id, src_step):
    for e in self.recipe.backward_out(src_step):    # loop edges leaving the step that just finished
        if not self._cond(e.when, item_id):
            continue                                # condition false → don't loop
        target = self.board.card(item_id, e.dst)
        if target.visits >= self.recipe.max_visits: # loop guard: give up after max_visits
            self.trace.event("loop-max", f"{item_id}:{e.dst}", visits=target.visits)
            continue
        ctx = self.board.context.setdefault(item_id, {})
        for sid in self.recipe.loop_body(e.dst, src_step):   # reset dst..src to run again
            c = self.board.card(item_id, sid)
            c.status = "todo"
            c.output = None
            if sid != src_step:                     # KEEP the source's output as feedback…
                ctx.pop(sid, None)                  # …but clear the rest so they truly re-run
        self.board.log_event(item_id, e.dst, "loop")
        self.trace.event("loop", f"{item_id}:{src_step}->{e.dst}", pass_=target.visits + 1)
```

When `verify` finishes with `fail`: the loop edge `verify → write` fires. It resets the **loop body**
(`write` and `verify`) back to `todo` and clears their outputs — *except* it keeps `verify`'s output in
`context`. That's the subtle, important part: `write` is about to re-run and its wiring reads
`verify.issues`, so verify's complaints must survive the reset to feed the revision. The guard
`visits >= max_visits` stops an endlessly-failing loop after 4 tries.

### 5.9 The small remaining methods

```python
def _fail(self, card, step, msg):        # a specialist raised → mark failed, log it
    card.status = "failed"; card.attempts.append({"error": msg}); ...

def _finalize(self):                     # after the loop: any card with no path to run is a skipped branch
    for card in self.board.with_status("todo", "ready"):
        if card.status == "ready":  continue
        card.status = "skipped"; ...

def approve(self, item_id, step_id, auto=False):   # resolve a gate: gated -> done, then check loops
    card = self.board.card(item_id, step_id)
    if not card or card.status != "gated":
        raise ValueError(f"{item_id}:{step_id} is not awaiting approval")
    card.status = "done"; self.board.log_event(...); self._fire_loops(item_id, step_id)

def _cond(self, when, item_id):          # evaluate an edge condition using our resolver
    return evaluate(when, lambda ref: self._resolve(ref, item_id))
```

`approve` is what a human (or `auto_approve`) calls to release a gate. In auto mode the main loop calls
it; interactively, `engine approve <run> <item> <step>` loads the board, makes a fresh Dispatcher, calls
`approve`, then `run()` again to drain whatever the approval unblocked.

### 5.10 How an edge condition is evaluated

`_cond` hands the condition string to `conditions.evaluate`, a tiny **safe** parser (no Python `eval`, so
a recipe can never execute arbitrary code). For `"verify.verdict == 'fail'"`:

1. It splits on the operator `==` into `verify.verdict` and `'fail'`.
2. The left side is a *reference* → resolved via our `_resolve`, i.e. `context[item]["verify"]["verdict"]`.
3. The right side `'fail'` is a quoted *literal* → the string `fail`.
4. It compares them and returns `True`/`False`.

A `when=None` (unconditional edge) short-circuits to `True`. That's the entire edge-condition language:
references on the left, literals/references on the right, `== != > < >= <= in`, joined by `and`/`or`/`not`.

---

## 6. One specialist in full: `verify`

Here is `verify` end to end (`specialists/verify.py`), the step that gates our loop.

```python
class Verify(Specialist):
    name = "verify"
    contract = Contract(
        input={"subject": object, "standard": str},
        output={"verdict": str, "confidence": float, "issues": list},
    )

    def _run(self, input, config):
        fs = block("verify", input)                 # (a) maybe retrieve few-shot examples
        prompt = (
            f"Judge whether the SUBJECT meets this standard: {input['standard']}\n\n"
            f"SUBJECT:\n{text_of(input['subject'])}\n\n"
            + (fs + "\n\n" if fs else "")
            + 'Return JSON: {"verdict": "pass" or "fail", "confidence": <0..1>, '
              '"issues": [<zero or more short problem strings>]}'
        )
        r = brain_json(prompt, system=SYSTEM, temperature=0.0)   # (b) call the model, get JSON
        verdict = "pass" if str(r.get("verdict", "")).lower().startswith("pass") else "fail"  # (c) normalize
        return {"verdict": verdict,                              # (d) return the contracted shape
                "confidence": num(r.get("confidence")),
                "issues": [str(x) for x in as_list(r.get("issues"))]}
```

Walking it:
- The Dispatcher calls `verify.run(card.input, step.config)`. `run()` (the base) merges them so `_run`
  sees `{subject: {...}, standard: "STRICT — ..."}` and validates that `subject` and `standard` are present.
- **(a)** `block("verify", input)` asks the few-shot system for example judgments. For `verify` the
  cached empirical policy is "few-shot OFF" (measured — a checker does worse with it), so this returns an
  empty string. It's still *called* uniformly; the decision is data-driven, not hardcoded.
- The prompt is assembled as plain text: the standard, the subject (rendered by `text_of`, which turns a
  dict into readable text), and an instruction to return specific JSON.
- **(b)** `brain_json(...)` is the model call. Under the hood (`core/brain.py`) it appends "Return ONLY
  valid JSON," calls `brain()` — which for the default `cli` backend shells out to `claude -p` as a
  **subprocess**, waits for stdout, and returns the text — then parses the JSON (stripping code fences,
  grabbing the first `{...}` block, retrying once if parsing fails).
- **(c)/(d)** It normalizes the verdict to exactly `"pass"`/`"fail"` and returns the contracted dict. The
  base `run()` then validates that shape before the value ever reaches the Dispatcher.

That returned dict is what the Dispatcher's `_commit` stores in `context["item"]["verify"]`, and it's
what the edge conditions `verify.verdict == 'fail'` / `== 'pass'` read to decide the branch.

The `write` specialist is similar but returns free text (`{"post": ...}`) via `brain()` (not
`brain_json`), and notably reads the optional `feedback` field — if a prior draft was flagged, it writes
a *new* draft that addresses the issues instead of starting fresh. That optional `feedback` input is the
other half of the loop.

---

## 7. The full trace: one work-item, every transition

Now we put it all together. Feed in one work-item:

```
item_id = "item"
payload = {"topic": "...", "sources": "...", "brief": "...", "slug": "post.txt"}
```

We'll assume `verify` **fails the first draft, passes the second** — the interesting case. Columns are
the three cards; each row is a moment in time.

| moment | write | verify | act | what the Dispatcher did |
|---|---|---|---|---|
| after `_intake` | todo | todo | todo | one card per step |
| `_submit_ready` #1 | **ready→running** | todo | todo | write has no prerequisites (entry step); inputs resolved (`feedback` → `None`, verify hasn't run); dispatched |
| write finishes | **done** | todo | todo | `_commit`: `context["write"]={"post": draft1}`; not a gate; no loops out of write |
| `_submit_ready` #2 | done | **ready→running** | todo | verify's prerequisite (write) is done; inputs resolved: `subject={draft: draft1, topic}`; dispatched |
| verify finishes (**fail**) | done | **done** | todo | `_commit`: `context["verify"]={"verdict":"fail","issues":[…]}`; then `_fire_loops` |
| loop fires | **todo** (output cleared) | **todo** (output *kept* in context) | todo | `verify→write` condition `verdict=='fail'` is true; `write` & `verify` reset; verify's `issues` preserved as feedback; `write.visits` still 1 < 4 |
| `_submit_ready` #3 | **ready→running** | todo | todo | write re-runs; this time `feedback` → verify's issues → it **revises** |
| write finishes | **done** | todo | todo | `context["write"]={"post": draft2}` |
| `_submit_ready` #4 | done | **ready→running** | todo | verify re-runs on draft2 |
| verify finishes (**pass**) | done | **done** (visits=2) | todo | `context["verify"]={"verdict":"pass","issues":[]}`; `_fire_loops`: `verdict=='fail'` now false → **no loop** |
| `_submit_ready` #5 | done | done | **ready→running** | `verify→act` condition `verdict=='pass'` is true → act ready; inputs `{content: draft2, name: "post.txt"}`; dispatched |
| act finishes | done | done | **gated** | `_commit`: act has `gate=True` → status `gated`, **stop**; run returns kind="pause" |
| — human approves — | done | done | **done** | `engine approve` → new Dispatcher → `approve("item","act")` → `run()` drains → board fully done |

A few things this trace makes concrete:

- **Scheduling is pull-based off the graph.** Nothing "calls" verify; verify becomes `ready` the moment
  `_readiness` sees its one prerequisite (`write`) is `done`. The Dispatcher never has workflow-specific
  logic — it just recomputes readiness after every completion.
- **The loop is a reset, not a recursion.** Firing the loop just flips `write`/`verify` back to `todo`
  and clears outputs; the normal readiness machinery then re-runs them. The only special care is keeping
  `verify.issues` alive so the revision can read it. `max_visits=4` caps it.
- **The branch cleans itself up.** When verify passes, the `fail` edge's target (`write`) is never marked
  ready again, and the un-taken path leaves no dangling `ready` card. (If the recipe had a step reachable
  only via the un-taken branch, `_finalize` would mark it `skipped`.)
- **The gate is a hard stop.** `act` finishing produces a `gated` card, the `while inflight` loop finds
  nothing left running and (without auto-approve) exits — the run *pauses*, fully checkpointed. Approval
  is a separate invocation that reconstructs the Dispatcher from the Board and drains the rest.
- **"Done" is just a function returning.** Every "finishes" above is: the specialist's `_run` returned a
  dict on a worker thread → the pool set that Future to done → the Dispatcher's `wait(FIRST_COMPLETED)`
  woke up → `_commit` ran.

---

## 8. The one-paragraph summary

A **Recipe** is a graph of **Steps** joined by **Edges** — the program. The **Board** holds a **Card**
for every (item, step) with a status, plus a `context` of each step's output — the memory, saved to disk
after every change. The **Dispatcher** is a generic interpreter: it lays down cards, then loops —
compute which cards are `ready` purely from the graph's forward edges, join rules, and edge conditions;
resolve each ready card's inputs by reading `payload` and prior steps' outputs from context; run the
matching **Specialist** on a worker thread; and when a Future signals the specialist returned, record its
output, fire any backward (loop) edges, and pause at any gate. It knows a step finished because the step
is an in-process function whose return wakes the thread it was parked on. All the intelligence lives in
the graph (drawn by us or the Composer) and in the specialists (which call the model); the Dispatcher in
between stays deliberately dumb, deterministic, and reusable — which is exactly why one engine runs every
workflow.

---

## 9. MCP interop — from scratch

The four-noun model above is exactly what makes it easy to connect the engine to the outside world without
disturbing anything. This section assumes you've never heard of MCP.

### 9.1 What MCP is, exactly

**The problem it solves.** An AI model is good at reasoning but can't *do* anything on its own — it can't
read your files, query a database, or hit an API. So every AI app had to hand-write an integration for
every tool it wanted to use. With N apps and M tools, that's N×M bespoke, incompatible integrations.

**MCP (Model Context Protocol)** is a standard that turns that into N + M. It's a *protocol* — a fixed
format for two programs to talk — created by Anthropic and now widely adopted. A tool provider writes
**one** "MCP server"; any "MCP client" can use it with no custom code. Think **USB-C for AI**: one plug
shape, any device.

There are always two roles:
- an **MCP server** *exposes* capabilities — mostly **tools** (a tool = a name, a description, a typed
  input schema, and it returns a result);
- an **MCP client** *consumes* them: it connects, asks "what tools do you have?" (discovery), and calls them.

They talk in JSON-RPC messages over a **transport**. Two common ones: **stdio** (the client launches the
server as a subprocess and they exchange messages over stdin/stdout — simplest, local; this is what the engine
uses) and **HTTP/SSE** (for remote servers). Concrete example you may have used: **Claude Desktop is an
MCP client** — point it at MCP servers (filesystem, GitHub, a company's internal server) and Claude can
call those tools mid-conversation.

### 9.2 How the engine has it — the key insight

**An engine specialist and an MCP tool are the same shape**: a named capability with typed inputs and
outputs. `classify` takes `{item, categories, criteria}` and returns `{label, …}`; an MCP tool takes a
typed input and returns a result — same idea. So interop is just a *mapping between the two*, in each
direction, and it all lives at the **edges** (the core — recipe / dispatcher / board / contracts — never
changed; the `mcp` SDK is an optional dependency that only loads if you use it):

- **IMPORT (the engine as client):** adopt an external MCP tool *as* an engine specialist.
- **EXPORT (the engine as server):** publish an engine specialist *as* an MCP tool.

### 9.3 Import — the `mcp_call` specialist

The client side is one new specialist, `mcp_call` — an I/O adapter like `fetch` and `act` (pure plumbing,
no model call). Its contract:

```
IN  {server, tool, arguments}  →  OUT {result}
```

To the **Dispatcher it is completely ordinary** — its card becomes `ready`, its inputs get resolved, it
runs on a worker thread, it commits a result, exactly like `classify`. The Dispatcher has **zero**
awareness that MCP exists. Inside, `mcp_call._run` does the MCP-specific work:

1. lazy-imports the client adapter (`engine/mcp/client.py`) — this is where the optional `mcp` SDK finally loads;
2. **launches the external MCP server as a subprocess** and opens a stdio connection to it;
3. runs the handshake (`initialize`), then **calls the named tool** with your arguments;
4. gets the result, normalizes it, tears the connection down, returns `{result: …}` — bounded by a
   `timeout` so a hung server can't wedge the workflow.

In a recipe it's just a step (the same `Step`/`inputs`/`config` machinery from §1):

```python
Step(id="pull", specialist="mcp_call",
     config={"server": {"command": "python", "args": ["some_server.py"]}, "tool": "top_items"},
     inputs={"arguments": "payload"})   # tool arguments pulled from the work item, like any wiring
```

That's the payoff of "specialists are just functions" (§3): a brand-new *kind* of capability — call any
external tool — needed **no engine change**.

### 9.4 Export — the MCP server

The server side is one entry point:

```bash
pip install -e '.[mcp]'
python -m engine.mcp.server        # a FastMCP server on stdio
```

On startup it **loops over the specialist library and registers each specialist as its own MCP tool** —
tool name = the specialist's name, description = its capability card — plus one higher-level tool,
`compose_and_run`, that runs the full compose → dispatch pipeline you traced in §7. An external MCP client
(Claude Desktop) launches this, discovers ~16 tools (`classify`, `summarize`, `forecast`, … +
`compose_and_run`), and can call any of them. Note the layering: a specialist is wrapped *by* the engine; the
server *wraps* the engine — the mirror image, which is why it's an entry point and not itself a specialist.

Wire it into Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "engine": { "command": "python", "args": ["-m", "engine.mcp.server"] } } }
```

### 9.5 Seeing both directions run

`examples/scripts/mcp_demo.py` proves it end to end, brain-free. Actual output:

```
=== IMPORT: a workflow step calls an external MCP tool ===
  pull step output: {'result': [{'id': '1', 'title': 'item 1'}, {'id': '2', 'title': 'item 2'}]}
      # a real recipe step pulled data from an external MCP server, through the real dispatcher

=== EXPORT: an MCP client uses the engine's specialists as MCP tools ===
  The engine exposes 16 MCP tools: [act, classify, compose_and_run, extract, fetch, forecast, match,
                               mcp_call, rank, respond, review, route, sequence, summarize, verify, write]
  called the engine's 'act' tool via MCP -> {'status': 'staged', 'result': {'wrote': 'output/mcp_demo.txt'}}
      # an MCP client discovered the engine's specialists and invoked one over the protocol
```

### 9.6 Four real use cases (A/B/C verified live on real public data)

The mock demo proves the plumbing; these show it doing real work. They share two tiny **bundled example MCP
servers** (`examples/mcp_servers/` — GitHub issues, Hacker News; ~40 lines of stdlib each over a public API),
which return the *same item shape* as the engine's native `fetch`, so everything runs with no secrets.

- **A — Triage a live GitHub tracker** (`examples/scripts/mcp_github_triage.py`). An `mcp_call` step pulls real open
  issues through the GitHub-issues MCP server; then the engine `classify`s / `route`s / `summarize`s each. The
  external tool does the I/O; the engine does the reasoning. (Live run correctly labeled an unpatched git-path
  issue `security` and set `escalate=True`.)
- **B — Symmetry made visible** (`examples/scripts/mcp_symmetry.py`). Pull Hacker News two ways — native
  `fetch(source=hn)` vs an external MCP `top_stories` tool — identical item shape, identical downstream
  `classify`. The recipe tail doesn't care which supplied the data: a specialist and an MCP tool *are* the
  same shape.
- **C — Server and client at once** (`examples/scripts/mcp_server_and_client.py`). Client → the engine's server → the
  official `@modelcontextprotocol/server-filesystem`. We call the engine's `mcp_call` tool to read a file (the engine
  is a *client*), then its `summarize` tool to reason over it (the engine is a *server*) — one process, both
  roles. This is why the server runs each specialist on `asyncio.to_thread`: an itself-async specialist like
  `mcp_call` must not run inside the server's event loop.
- **D — Drive the engine from Claude Desktop** (`docs/mcp.md`). Add one entry to `claude_desktop_config.json` and
  Claude Desktop's own model calls the engine's tools. The tool-calling path is broadly supported. (~2 min, manual.)

### 9.7 Why it's safe / modular

- **Optional dependency** — `pip install engine` has no MCP; `pip install -e '.[mcp]'` adds it.
- **Lazy** — even with the SDK installed, nothing MCP loads until a tool is actually called or the server
  is started (verified).
- **Core untouched** — the composer, dispatcher, contracts, and even `fetch` are byte-for-byte unchanged;
  all MCP code is `engine/mcp/` + the one `mcp_call` specialist (the use cases added only `examples/`).
- **Tested** — `tests/test_mcp.py` runs both directions over the real protocol and skips cleanly if `mcp`
  isn't installed, so the base suite stays green either way.

**In one line:** the engine can use anyone's MCP tools inside a workflow, and expose its own specialists and
workflows as MCP tools to anyone — proven on live GitHub, Hacker News, and filesystem data. A clean,
optional, edge-only layer. Full reference: `docs/mcp.md`.
