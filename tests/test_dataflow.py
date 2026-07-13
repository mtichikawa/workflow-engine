"""The data-flow extractor: a recipe's step `inputs` become the true data graph (fan-out/fan-in),
its edges become control edges. Pure — no brain."""

from engine.core import Edge, Recipe, Step
from engine.core.dataflow import dataflow


def test_fanout_fanin_and_terminal():
    r = Recipe(name="t", steps=[
        Step(id="a", specialist="classify", inputs={"item": "payload"}),
        Step(id="b", specialist="rank", inputs={"item": "payload"}),
        Step(id="c", specialist="verify", inputs={"subject": {"x": "a.label", "y": "b.score"}}),
    ], edges=[Edge("a", "b"), Edge("b", "c")])
    g = dataflow(r)

    assert {n["id"] for n in g["nodes"]} == {"IN", "a", "b", "c", "OUT"}
    de = {(e["src"], e["dst"]) for e in g["data_edges"]}
    assert ("IN", "a") in de and ("IN", "b") in de      # fan-out: payload → both readers
    assert ("a", "c") in de and ("b", "c") in de        # fan-in: a + b → c
    assert ("c", "OUT") in de                            # terminal step → OUT
    # payload reads are labeled from their field (default "issue"); step reads carry the field
    reads = {(e["src"], e["dst"]): e["reads"] for e in g["data_edges"]}
    assert reads[("a", "c")] == "label" and reads[("b", "c")] == "score"


def test_control_edges_carry_guards():
    r = Recipe(name="t", steps=[
        Step(id="w", specialist="write", inputs={"topic": "payload"}),
        Step(id="v", specialist="verify", inputs={"subject": {"d": "w.post"}}),
    ], edges=[Edge("w", "v"), Edge("v", "w", "v.verdict == 'fail'")])   # a loop
    g = dataflow(r)
    ce = {(e["src"], e["dst"]): e["when"] for e in g["control_edges"]}
    assert ce[("w", "v")] is None
    assert ce[("v", "w")] == "v.verdict == 'fail'"       # the loop-back guard is preserved
