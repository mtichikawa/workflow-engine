"""A deliberately COMPLEX graph, to exercise the visualization: fan-out -> AND-join ->
a refine<->verify loop -> a gated publish. Fast dummy specialists (no brain), so it runs
instantly and deterministically.

    python examples/complex_demo.py     # writes output/replay-qa-demo.html
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.core import (Board, Contract, Dispatcher, Edge, Recipe, Specialist,
                        Step, Tracer, register, validate)
from engine.replay import build


class Emit(Specialist):
    name = "d_emit"
    contract = Contract(input={}, output={"v": object})
    def _run(self, input, config): return {"v": config.get("v", "·")}

class Collect(Specialist):
    name = "d_collect"
    contract = Contract(input={}, output={"got": object})
    def _run(self, input, config): return {"got": dict(input)}

class Gen(Specialist):
    name = "d_gen"
    contract = Contract(input={}, output={"n": object})
    def _run(self, input, config): return {"n": (input.get("prev") or 0) + 1}

class Check(Specialist):
    name = "d_check"
    contract = Contract(input={"n": object}, output={"ok": object, "last": object})
    def _run(self, input, config):
        return {"ok": input["n"] >= config["target"], "last": input["n"]}

for s in (Emit(), Collect(), Gen(), Check()):
    register(s)


RECIPE = Recipe("qa-pipeline",
    steps=[
        Step("intake", "d_emit", config={"v": "item"}),
        Step("scan_a", "d_emit", config={"v": "A"}),
        Step("scan_b", "d_emit", config={"v": "B"}),
        Step("scan_c", "d_emit", config={"v": "C"}),
        Step("merge", "d_collect", join="and",
             inputs={"a": "scan_a.v", "b": "scan_b.v", "c": "scan_c.v"}),
        Step("refine", "d_gen", inputs={"prev": "verify.last"}),
        Step("verify", "d_check", config={"target": 3}, inputs={"n": "refine.n"}),
        Step("publish", "d_collect", gate=True,
             inputs={"result": "refine.n", "scans": "merge.got"}),
    ],
    edges=[
        Edge("intake", "scan_a"), Edge("intake", "scan_b"), Edge("intake", "scan_c"),  # fan-out
        Edge("scan_a", "merge"), Edge("scan_b", "merge"), Edge("scan_c", "merge"),      # AND-join
        Edge("merge", "refine"), Edge("refine", "verify"),
        Edge("verify", "refine", "verify.ok == false"),   # loop: refine until it passes
        Edge("verify", "publish", "verify.ok == true"),   # then publish (gated)
    ])


def main():
    print("validator:")
    for f in validate(RECIPE):
        print("  ", f)
    board = Board("qa-pipeline", "qa-demo")
    for i in range(3):
        board.add_item(f"item{i + 1}", {"title": f"work item {i + 1}"})
    Dispatcher(RECIPE, board, Tracer("qa-demo", echo=False), concurrency=4).run(auto_approve=True)
    print(f"\nran 3 items, {len(board.events)} events")
    Path("output").mkdir(exist_ok=True)
    Path("output/replay-qa-demo.html").write_text(build(board, RECIPE))
    print("wrote output/replay-qa-demo.html")
    # sanity: all published
    pub = [board.card(i, "publish").status for i in board.items]
    print("publish statuses:", pub)


if __name__ == "__main__":
    main()
