"""Gates (approve / reject, and work waiting behind a gate) and the brain tape (record / replay).

Deterministic: dummy specialists for the gate, a stubbed live call for the tape — no brain.
"""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from engine.core import (Board, Contract, Dispatcher, Edge, Recipe, Specialist, Step, Tracer,
                         brain, register, tape)
from engine.core.tape import TapeMiss

BRAIN = importlib.import_module("engine.core.brain")    # the module (engine.core.brain is also the function)


class Make(Specialist):
    name = "gt_make"
    contract = Contract(input={}, output={"v": object})
    def _run(self, input, config): return {"v": "draft"}

class Ship(Specialist):
    name = "gt_ship"
    contract = Contract(input={}, output={"shipped": object})
    def _run(self, input, config): return {"shipped": input.get("v")}

for s in (Make(), Ship()):
    register(s)

GATED = Recipe("gated", steps=[Step("make", "gt_make", gate=True), Step("ship", "gt_ship", inputs={"v": "make.v"})],
               edges=[Edge("make", "ship")])


def _paused(tmp_path):
    board = Board("gated", "gt", state_dir=tmp_path)
    board.add_item("i1", {})
    disp = Dispatcher(GATED, board, Tracer("gt", log_dir=tmp_path, echo=False))
    disp.run()
    return board, disp


def test_work_behind_a_gate_waits_instead_of_being_skipped(tmp_path):
    board, _ = _paused(tmp_path)
    assert board.card("i1", "make").status == "gated"
    assert board.card("i1", "ship").status == "todo"          # undecided until a person acts


def test_approve_runs_what_was_waiting(tmp_path):
    board, disp = _paused(tmp_path)
    disp.approve("i1", "make")
    disp.run()
    assert board.card("i1", "ship").status == "done"
    assert board.context["i1"]["ship"] == {"shipped": "draft"}


def test_reject_skips_what_was_waiting(tmp_path):
    board, disp = _paused(tmp_path)
    disp.reject("i1", "make", "not good enough")
    disp.run()
    assert board.card("i1", "make").status == "rejected"
    assert board.card("i1", "ship").status == "skipped"
    assert board.card("i1", "make").attempts[-1] == {"rejected": "not good enough"}


def test_cards_record_how_long_each_pass_took(tmp_path):
    board, _ = _paused(tmp_path)
    card = board.card("i1", "make")
    assert card.started and card.seconds is not None and card.seconds >= 0


def test_tape_replays_exactly_what_it_recorded(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(BRAIN, "_brain",
                        lambda p, s, t, pr, f=None: calls.append(p) or f"answer to {p}")
    path = tmp_path / "tape.json"
    with tape.recording(path) as t:
        assert brain("one") == "answer to one"
        assert brain("two", system="sys") == "answer to two"
    t.save()
    assert len(calls) == 2
    with tape.replaying(path, pace=0) as r:
        assert brain("two", system="sys") == "answer to two"     # order doesn't matter
        assert brain("one") == "answer to one"
    assert len(calls) == 2                                        # nothing went to the model
    assert [c["served"] for c in r.log] == ["exact", "exact"]


def test_tape_misses_loudly_and_matches_a_drifted_prompt_only_as_approx(tmp_path, monkeypatch):
    monkeypatch.setattr(BRAIN, "_brain", lambda p, s, t, pr, f=None: "x")
    path = tmp_path / "tape.json"
    prompt = "catalog: classify runs=12 rank runs=4 " * 20
    with tape.recording(path) as t:
        brain(prompt)
    t.save()
    with tape.replaying(path, pace=0) as r:
        assert brain(prompt.replace("runs=12", "runs=13")) == "x"
        with pytest.raises(TapeMiss):
            brain("something never recorded")
    assert [c["served"] for c in r.log] == ["approx", "miss"]


def test_tape_keys_include_the_images(tmp_path, monkeypatch):
    monkeypatch.setattr(BRAIN, "_brain", lambda p, s, t, pr, f=None: f"saw {Path(f[0]).read_text()}")
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_text("A")
    b.write_text("B")
    path = tmp_path / "tape.json"
    with tape.recording(path) as t:
        brain("read it", files=[str(a)])
    t.save()
    a.write_text("changed")                                       # same words, different scan
    with tape.replaying(path, pace=0):
        with pytest.raises(TapeMiss):
            brain("read it", files=[str(a)])
