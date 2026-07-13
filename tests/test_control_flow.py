"""Control-flow correctness: branches, OR/AND joins, and guarded loops.

Deterministic dummy specialists (no brain) so each graph shape is proven exactly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.core import (Board, Contract, Dispatcher, Edge, Recipe, Specialist,
                        Step, Tracer, register)


class Emit(Specialist):
    name = "cf_emit"
    contract = Contract(input={}, output={"v": object})
    def _run(self, input, config): return {"v": config.get("v", "?")}

class Collect(Specialist):
    name = "cf_collect"
    contract = Contract(input={}, output={"got": object})
    def _run(self, input, config): return {"got": dict(input)}

class Gen(Specialist):
    name = "cf_gen"
    contract = Contract(input={}, output={"n": object})
    def _run(self, input, config): return {"n": (input.get("prev") or 0) + 1}

class Check(Specialist):
    name = "cf_check"
    contract = Contract(input={"n": object}, output={"ok": object, "last": object})
    def _run(self, input, config):
        return {"ok": input["n"] >= config["target"], "last": input["n"]}

for s in (Emit(), Collect(), Gen(), Check()):
    register(s)


def _run(recipe, payload=None, concurrency=1):
    board = Board(recipe.name, f"cf-{recipe.name}-{id(recipe)}")
    board.add_item("i1", payload or {})
    Dispatcher(recipe, board, Tracer(f"cf-{recipe.name}", echo=False), concurrency=concurrency).run(True)
    return board


def test_branch():
    # pick emits "A"; only the matching out-edge is taken, the other card is skipped
    r = Recipe("branch",
               steps=[Step("pick", "cf_emit", config={"v": "A"}),
                      Step("a", "cf_collect"), Step("b", "cf_collect")],
               edges=[Edge("pick", "a", "pick.v == 'A'"), Edge("pick", "b", "pick.v == 'B'")])
    b = _run(r)
    assert b.card("i1", "a").status == "done"
    assert b.card("i1", "b").status == "skipped"


def test_or_join():
    # two branches reconverge; the OR-join runs once, on the branch that was taken
    r = Recipe("orjoin",
               steps=[Step("pick", "cf_emit", config={"v": "A"}),
                      Step("a", "cf_collect"), Step("b", "cf_collect"),
                      Step("merge", "cf_collect", join="or")],
               edges=[Edge("pick", "a", "pick.v == 'A'"), Edge("pick", "b", "pick.v == 'B'"),
                      Edge("a", "merge"), Edge("b", "merge")])
    b = _run(r)
    assert b.card("i1", "b").status == "skipped"
    assert b.card("i1", "merge").status == "done"


def test_and_join():
    # three parallel steps fan in; synth waits for ALL, then combines them
    r = Recipe("andjoin",
               steps=[Step("start", "cf_emit", config={"v": "go"}),
                      Step("a", "cf_emit", config={"v": "A"}),
                      Step("b", "cf_emit", config={"v": "B"}),
                      Step("c", "cf_emit", config={"v": "C"}),
                      Step("synth", "cf_collect", join="and",
                           inputs={"a": "a.v", "b": "b.v", "c": "c.v"})],
               edges=[Edge("start", "a"), Edge("start", "b"), Edge("start", "c"),
                      Edge("a", "synth"), Edge("b", "synth"), Edge("c", "synth")])
    b = _run(r, concurrency=3)
    assert b.card("i1", "synth").status == "done"
    assert b.context["i1"]["synth"]["got"] == {"a": "A", "b": "B", "c": "C"}


def test_loop_converges():
    # gen increments each pass (reading the kept feedback); loops until check passes
    r = Recipe("loop",
               steps=[Step("gen", "cf_gen", inputs={"prev": "check.last"}),
                      Step("check", "cf_check", config={"target": 3}, inputs={"n": "gen.n"})],
               edges=[Edge("gen", "check"), Edge("check", "gen", "check.ok == false")])
    b = _run(r)
    assert b.context["i1"]["check"]["last"] == 3
    assert b.context["i1"]["check"]["ok"] is True
    assert b.card("i1", "gen").visits == 3


def test_loop_guard():
    # never satisfies -> stops at max_visits, not forever
    r = Recipe("loopguard", max_visits=4,
               steps=[Step("gen", "cf_gen", inputs={"prev": "check.last"}),
                      Step("check", "cf_check", config={"target": 99}, inputs={"n": "gen.n"})],
               edges=[Edge("gen", "check"), Edge("check", "gen", "check.ok == false")])
    b = _run(r)
    assert b.card("i1", "gen").visits == 4
    assert b.context["i1"]["check"]["ok"] is False
