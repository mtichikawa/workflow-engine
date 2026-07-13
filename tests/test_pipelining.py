"""Proves TRUE pipelining: a fast item reaches stage 2 before a slow item finishes
stage 1. Under the old wave model that's impossible (a barrier holds stage 2 until
every item clears stage 1). Records completion times and asserts the ordering.

Run:  python tests/test_pipelining.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.core import (Board, Contract, Dispatcher, Recipe, Specialist, Step,
                        Tracer, register)

DONE_AT: dict = {}


class Timed(Specialist):
    name = "timed"
    contract = Contract(input={"delay": object, "n": object}, output={"n": object})

    def _run(self, input, config):
        time.sleep(float(input["delay"]))
        DONE_AT[(input["n"], config["stage"])] = time.time()
        return {"n": input["n"]}


register(Timed())

RECIPE = Recipe("pipe", [
    Step(id="s1", specialist="timed", config={"stage": "s1"},
         inputs={"delay": "payload.d1", "n": "payload.n"}),
    Step(id="s2", specialist="timed", config={"stage": "s2"},
         inputs={"delay": "payload.d2", "n": "s1.n"}),
])


def main():
    board = Board("pipe", "pipe-test")
    board.add_item("A", {"n": "A", "d1": 0.05, "d2": 0.05})   # fast
    board.add_item("B", {"n": "B", "d1": 0.80, "d2": 0.05})   # slow on stage 1
    Dispatcher(RECIPE, board, Tracer("pipe-test", echo=False), concurrency=2).run()

    a_s2 = DONE_AT[("A", "s2")]
    b_s1 = DONE_AT[("B", "s1")]
    assert a_s2 < b_s1, "A did not reach stage 2 before B finished stage 1 — not pipelined!"
    assert all(board.card(i, s).status == "done" for i in ("A", "B") for s in ("s1", "s2"))
    print(f"OK — A cleared BOTH stages {b_s1 - a_s2:.2f}s before B even finished stage 1. "
          "True pipelined dispatch: fast items race ahead, no barrier.")


if __name__ == "__main__":
    main()
