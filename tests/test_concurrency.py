"""Concurrency: ready cards run in parallel, and results are identical to sequential.

Uses a specialist that sleeps, so wall-clock proves parallelism without any brain calls.
Run:  python tests/test_concurrency.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.core import (Board, Contract, Dispatcher, Recipe, Specialist, Step,
                        Tracer, register)

SLEEP = 0.4
N = 5


class Sleeper(Specialist):
    name = "sleeper"
    contract = Contract(input={"n": int}, output={"n": int, "sq": int})

    def _run(self, input, config):
        time.sleep(SLEEP)
        return {"n": input["n"], "sq": input["n"] ** 2}


register(Sleeper())
RECIPE = Recipe("sleep", [Step(id="sleeper", specialist="sleeper", inputs={"n": "payload.n"})])


def run(concurrency: int) -> tuple[float, dict]:
    board = Board("sleep", f"sleep-c{concurrency}")
    for i in range(N):
        board.add_item(f"i{i}", {"n": i})
    t0 = time.time()
    Dispatcher(RECIPE, board, Tracer(f"sleep-c{concurrency}", echo=False), concurrency=concurrency).run()
    elapsed = time.time() - t0
    outputs = {i: board.context[i]["sleeper"]["sq"] for i in board.items}
    return elapsed, outputs


def main():
    seq_t, seq_out = run(1)
    par_t, par_out = run(N)
    print(f"sequential ({N} items): {seq_t:.2f}s")
    print(f"parallel   ({N} items): {par_t:.2f}s")
    assert seq_out == par_out == {f"i{i}": i * i for i in range(N)}, "results differ!"
    assert seq_t > SLEEP * N * 0.8, "sequential wasn't actually serial?"
    assert par_t < SLEEP * 2, f"parallel not fast enough ({par_t:.2f}s)"
    print(f"\nOK — identical results; parallel ~{seq_t / par_t:.1f}x faster, same board writes.")


if __name__ == "__main__":
    main()
