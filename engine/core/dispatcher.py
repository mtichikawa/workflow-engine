"""Dispatcher — runs a recipe GRAPH against the board.

Pull-based, pipelined, and mechanical: it makes no domain decisions and owns every board
write (specialists are pure), so parallel workers never clobber shared state. "What runs
next" is driven entirely by the recipe's edges:

  - a step is READY when its forward in-edges are satisfied per its join (`and` = all,
    `or` = the first); a branch not taken leaves a card SKIPPED;
  - a DONE step fires its backward edges (loops), resetting the loop body to re-run (the
    source's output is preserved as feedback), bounded by `max_visits`.

The dispatcher only follows edges — all correctness lives in how the graph was drawn
(and is checked by the Validator before this ever runs).
"""

from __future__ import annotations

from . import specialist as registry
from .board import Board
from .conditions import evaluate
from .recipe import Recipe, Step
from .trace import Tracer

_TERMINAL = ("done", "skipped", "failed")


class Dispatcher:
    def __init__(self, recipe: Recipe, board: Board, tracer: Tracer, concurrency: int = 1):
        self.recipe = recipe
        self.board = board
        self.trace = tracer
        self.concurrency = concurrency

    # ---- the loop -------------------------------------------------------
    def run(self, auto_approve: bool = False) -> Board:
        from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

        self.trace.event("run", f"recipe={self.recipe.name}",
                         items=len(self.board.items), mode="pipelined")
        self._intake()
        with ThreadPoolExecutor(max_workers=max(1, self.concurrency)) as pool:
            inflight: dict = {}
            self._submit_ready(pool, inflight)
            while inflight:
                done, _ = wait(set(inflight), return_when=FIRST_COMPLETED)
                for fut in done:
                    card, step = inflight.pop(fut)
                    try:
                        self._commit(card, step, fut.result())
                    except Exception as e:  # noqa: BLE001
                        self._fail(card, step, str(e))
                self._submit_ready(pool, inflight)
                self.board.save()
                if not inflight:
                    gated = self.board.with_status("gated")
                    if gated and auto_approve:
                        for c in gated:
                            self.approve(c.item_id, c.step_id, auto=True)
                        self._submit_ready(pool, inflight)
        self._finalize()
        self.board.save()
        kind = "pause" if self.board.with_status("gated") else "done"
        self.trace.event(kind, "waiting on gates" if kind == "pause" else "board drained",
                         snapshot=self.board.snapshot())
        return self.board

    # ---- intake: every step gets a card up front ------------------------
    def _intake(self) -> None:
        for item_id in self.board.items:
            if not self.board.cards_for(item_id):
                for s in self.recipe.steps:
                    self.board.add_card(item_id, s.id, "todo")

    # ---- readiness: driven by forward in-edges + joins + conditions -----
    def _promote(self) -> None:
        for card in self.board.with_status("todo"):
            status = self._readiness(card.item_id, card.step_id)
            if status:
                card.status = status
                if status == "skipped":
                    self.board.log_event(card.item_id, card.step_id, "skipped")

    def _readiness(self, item_id: str, step_id: str) -> str | None:
        fin = self.recipe.forward_in(step_id)
        if not fin:
            return "ready"                                  # entry step
        results = []                                        # (resolved, satisfied)
        for e in fin:
            src = self.board.card(item_id, e.src)
            src_status = src.status if src else "todo"
            resolved = src_status in _TERMINAL
            satisfied = src_status == "done" and self._cond(e.when, item_id)
            results.append((resolved, satisfied))
        join = self.recipe.step(step_id).join
        if join == "or":
            if any(sat for _, sat in results):
                return "ready"
            if all(res for res, _ in results):
                return "skipped"                            # every branch resolved, none taken
        else:                                               # and
            if all(sat for _, sat in results):
                return "ready"
            if any(res and not sat for res, sat in results):
                return "skipped"                            # a required in-edge resolved false
        return None                                         # still waiting on a source

    def _submit_ready(self, pool, inflight: dict) -> None:
        import contextvars
        self._promote()
        slots = self.concurrency - len(inflight)
        for card in self.board.with_status("ready"):
            if slots <= 0:
                break
            step = self.recipe.step(card.step_id)
            try:
                card.input = self._resolve_input(step, card.item_id)
            except Exception as e:  # noqa: BLE001
                self._fail(card, step, f"input resolution: {e}")
                continue
            card.status = "running"
            # copy_context so the ambient scope (and any contextvar) propagates into the worker
            # thread — ThreadPoolExecutor does NOT do this by default, so few-shot in a threaded
            # specialist would otherwise ignore --scope.
            ctx = contextvars.copy_context()
            inflight[pool.submit(ctx.run, self._execute, card, step)] = (card, step)
            slots -= 1

    @staticmethod
    def _execute(card, step):
        return registry.get(step.specialist).run(card.input, step.config)

    # ---- commit + loops -------------------------------------------------
    def _commit(self, card, step, output) -> None:
        card.output = output
        card.attempts.append({"output": output})            # per-pass history (loops accumulate; display-only, feedback still uses latest)
        card.visits += 1
        card.coverage = self._coverage(step, card.input)     # tailored-vs-baseline few-shot split
        self.board.record_output(card.item_id, step.id, output)
        if step.gate:
            card.status = "gated"
            self.board.log_event(card.item_id, step.id, "gated")
            self.trace.event("GATE", f"{card.item_id}:{step.id}", out=output)
            return
        card.status = "done"
        self.board.log_event(card.item_id, step.id, "done")
        self.trace.event(step.id, card.item_id, out=output)
        self._fire_loops(card.item_id, step.id)

    @staticmethod
    def _coverage(step, resolved_input):
        """Record the few-shot layer split (tailored vs baseline) for this card. Uniform across
        specialists; None when no tenant scope is active or the specialist uses no few-shot."""
        try:
            from ..fewshot import coverage
            return coverage(step.specialist, resolved_input or {})
        except Exception:  # noqa: BLE001 — telemetry must never break a run
            return None

    def _fire_loops(self, item_id: str, src_step: str) -> None:
        for e in self.recipe.backward_out(src_step):
            if not self._cond(e.when, item_id):
                continue
            target = self.board.card(item_id, e.dst)
            if target.visits >= self.recipe.max_visits:
                self.trace.event("loop-max", f"{item_id}:{e.dst}", visits=target.visits)
                continue
            ctx = self.board.context.setdefault(item_id, {})
            for sid in self.recipe.loop_body(e.dst, src_step):
                c = self.board.card(item_id, sid)
                c.status = "todo"
                c.output = None
                if sid != src_step:                 # keep the source's output as feedback
                    ctx.pop(sid, None)
            self.board.log_event(item_id, e.dst, "loop")
            self.trace.event("loop", f"{item_id}:{src_step}->{e.dst}", pass_=target.visits + 1)

    def _fail(self, card, step, msg: str) -> None:
        card.status = "failed"
        card.attempts.append({"error": msg})
        self.board.log_event(card.item_id, step.id, "failed")
        self.trace.event("FAIL", f"{card.item_id}:{step.id}", err=msg)

    def _finalize(self) -> None:
        # any card still waiting with no path to run is a branch that was never taken
        for card in self.board.with_status("todo", "ready"):
            if card.status == "ready":
                continue
            card.status = "skipped"
            self.board.log_event(card.item_id, card.step_id, "skipped")

    # ---- gates ----------------------------------------------------------
    def approve(self, item_id: str, step_id: str, auto: bool = False) -> None:
        card = self.board.card(item_id, step_id)
        if not card or card.status != "gated":
            raise ValueError(f"{item_id}:{step_id} is not awaiting approval")
        card.status = "done"
        self.board.log_event(item_id, step_id, "done")
        self.trace.event("approve", f"{item_id}:{step_id}", auto=auto)
        self._fire_loops(item_id, step_id)

    # ---- conditions + input resolution ----------------------------------
    def _cond(self, when: str | None, item_id: str) -> bool:
        return evaluate(when, lambda ref: self._resolve(ref, item_id))

    def _resolve_input(self, step: Step, item_id: str) -> dict:
        return {field: self._resolve_expr(expr, item_id) for field, expr in step.inputs.items()}

    def _resolve_expr(self, expr, item_id: str):
        if isinstance(expr, dict):
            return {k: self._resolve_expr(v, item_id) for k, v in expr.items()}
        if isinstance(expr, list):
            return [self._resolve_expr(e, item_id) for e in expr]
        return self._resolve(expr, item_id)

    def _resolve(self, expr: str, item_id: str):
        head, _, tail = expr.partition(".")
        ctx = self.board.context.get(item_id, {})
        if head == "payload":
            base = self.board.items[item_id]["payload"]
        elif head in ctx:
            base = ctx[head]
        elif any(s.id == head for s in self.recipe.steps):
            return None                       # a real step with no output yet (loop feedback / optional)
        else:
            return expr                       # literal value (e.g. a filename)
        if base is None or not tail:
            return base
        for key in tail.split("."):
            if not isinstance(base, dict):
                return None
            base = base.get(key)
        return base
