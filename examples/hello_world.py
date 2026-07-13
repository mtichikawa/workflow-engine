"""Phase-1 validation: the engine runs a recipe end-to-end with dummy specialists.

Exercises: multi-item hopper (Model B), step sequencing, input resolution (adapter
layer), a gate, and the trace — with NO brain calls, so it's fast and deterministic.
Run:  python tests/hello_world.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.core import (Board, Contract, Dispatcher, Recipe, Specialist, Step,
                        Tracer, register)


class Greet(Specialist):
    name = "greet"
    kind = "capability"
    contract = Contract(input={"name": str}, output={"greeting": str})

    def _run(self, input, config):
        return {"greeting": f"hello, {input['name']}"}


class Publish(Specialist):
    name = "publish"
    kind = "domain"
    contract = Contract(input={"greeting": str}, output={"status": str})

    def _run(self, input, config):
        return {"status": f"STAGED: {input['greeting']!r} (mode={config.get('mode')})"}


register(Greet())
register(Publish())

recipe = Recipe(name="hello", steps=[
    Step(id="greet", specialist="greet", inputs={"name": "payload.name"}),
    Step(id="publish", specialist="publish", inputs={"greeting": "greet.greeting"},
         config={"mode": "staged"}, gate=True, domain=True),
])

board = Board(recipe="hello", run_id="hello-test")
board.add_item("i1", {"name": "Mike"})
board.add_item("i2", {"name": "world"})     # Model B: two items in the hopper at once

Dispatcher(recipe, board, Tracer("hello-test")).run(auto_approve=True)

# assertions
done = [c for c in board.cards.values() if c.status == "done"]
assert len(done) == 4, f"expected 4 done cards, got {len(done)}: {board.snapshot()}"
assert board.context["i1"]["greet"]["greeting"] == "hello, Mike"
assert "STAGED" in board.context["i2"]["publish"]["status"]
print("\nOK — engine ran 2 items through greet -> [gate] publish, all 4 cards done.")
