"""Unit tests for the core engine — fast, deterministic, no brain calls.

Covers contracts, the board, input resolution (the adapter layer), gates, failure
propagation, multi-item flow, brain-JSON parsing, and the registry.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.core import (Board, Contract, ContractViolation, Dispatcher, Recipe,
                        Specialist, Step, Tracer, get, register)
from engine.core.brain import _parse_json


# ---- dummy specialists (pure, no brain) --------------------------------
class Producer(Specialist):
    name = "t_producer"
    contract = Contract(input={}, output={"a": int, "b": int})
    def _run(self, input, config): return {"a": 1, "b": 2}

class Capture(Specialist):
    name = "t_capture"
    contract = Contract(input={}, output={"got": object})
    def _run(self, input, config): return {"got": dict(input)}

class Boom(Specialist):
    name = "t_boom"
    contract = Contract(input={}, output={"x": int})
    def _run(self, input, config): raise RuntimeError("kaboom")

for s in (Producer(), Capture(), Boom()):
    register(s)


def _dispatch(recipe, items, **kw):
    board = Board(recipe.name, f"test-{recipe.name}-{id(items)}")
    for iid, payload in items:
        board.add_item(iid, payload)
    Dispatcher(recipe, board, Tracer(board.run_id, echo=False), **kw).run(auto_approve=kw.pop("auto", False))
    return board


# ---- contracts ----------------------------------------------------------
def test_contract_ok():
    Contract(input={"x": int}, output={}).validate_input({"x": 1})

def test_contract_missing():
    try:
        Contract(input={"x": int}, output={}).validate_input({})
    except ContractViolation:
        return
    raise AssertionError("expected ContractViolation for missing field")

def test_contract_wrong_type():
    try:
        Contract(input={"x": int}, output={}).validate_input({"x": "nope"})
    except ContractViolation:
        return
    raise AssertionError("expected ContractViolation for wrong type")


# ---- board --------------------------------------------------------------
def test_board_roundtrip():
    b = Board("r", "test-roundtrip")
    b.add_item("i1", {"k": "v"})
    b.add_card("i1", "s1", "done")
    b.record_output("i1", "s1", {"o": 9})
    b.save()
    b2 = Board.load("test-roundtrip")
    assert b2.items["i1"]["payload"] == {"k": "v"}
    assert b2.card("i1", "s1").status == "done"
    assert b2.context["i1"]["s1"] == {"o": 9}

def test_board_snapshot():
    b = Board("r", "test-snap")
    b.add_card("i1", "s1", "done"); b.add_card("i1", "s2", "gated")
    snap = b.snapshot()
    assert snap["done"] == ["i1:s1"] and snap["gated"] == ["i1:s2"]


# ---- registry -----------------------------------------------------------
def test_registry_unknown():
    try:
        get("does-not-exist")
    except KeyError:
        return
    raise AssertionError("expected KeyError for unknown specialist")


# ---- brain JSON parsing -------------------------------------------------
def test_parse_bare():
    assert _parse_json('{"a": 1}') == {"a": 1}

def test_parse_fenced():
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}

def test_parse_embedded():
    assert _parse_json('Sure! {"a": 1} hope that helps') == {"a": 1}


# ---- dispatcher: sequencing, resolution, gates, failure, multi-item -----
def test_sequencing_and_resolution():
    recipe = Recipe("seq", [
        Step(id="step1", specialist="t_producer", inputs={}),
        Step(id="step2", specialist="t_capture", inputs={
            "whole": "step1", "just_a": "step1.a", "pay": "payload.k",
            "comp": {"nested": "step1.b"}, "lst": ["payload.k", "step1.a"], "lit": "literal-value"}),
    ])
    b = _dispatch(recipe, [("i1", {"k": 42})])
    got = b.context["i1"]["step2"]["got"]
    assert got["whole"] == {"a": 1, "b": 2}
    assert got["just_a"] == 1
    assert got["pay"] == 42
    assert got["comp"] == {"nested": 2}
    assert got["lst"] == [42, 1]
    assert got["lit"] == "literal-value"   # non-payload/non-step string -> literal

def test_gate_and_approve():
    recipe = Recipe("g", [
        Step(id="a", specialist="t_producer"),
        Step(id="b", specialist="t_capture", inputs={"x": "a.a"}, gate=True),
    ])
    b = _dispatch(recipe, [("i1", {})])
    assert b.card("i1", "b").status == "gated"          # paused, not done
    disp = Dispatcher(recipe, b, Tracer("g2", echo=False))
    disp.approve("i1", "b")
    assert b.card("i1", "b").status == "done"

def test_failure_blocks_downstream():
    recipe = Recipe("f", [
        Step(id="boom", specialist="t_boom"),
        Step(id="after", specialist="t_capture"),
    ])
    b = _dispatch(recipe, [("i1", {})])
    assert b.card("i1", "boom").status == "failed"
    assert b.card("i1", "after").status == "skipped"    # downstream of a failure is skipped, not run

def test_multi_item():
    recipe = Recipe("m", [Step(id="p", specialist="t_producer")])
    b = _dispatch(recipe, [("i1", {}), ("i2", {}), ("i3", {})])
    assert all(b.card(i, "p").status == "done" for i in ("i1", "i2", "i3"))
