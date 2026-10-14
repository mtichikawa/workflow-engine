"""Review at the gate: what a person decides, and what the engine learns from it.

Deterministic: dummy specialists, examples and logs written under tmp_path — no brain.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import pytest

from engine import examples, fewshot, review
from engine.core import Board, Contract, Dispatcher, Edge, Recipe, Specialist, Step, Tracer, register


class Label(Specialist):
    name = "rv_label"
    contract = Contract(input={"text": str}, output={"label": str, "confidence": float})
    def _run(self, input, config):
        return {"label": "billing", "confidence": 0.9 if "sure" in input["text"] else 0.4}

class Send(Specialist):
    name = "rv_send"
    contract = Contract(input={}, output={"sent": object})
    def _run(self, input, config): return {"sent": input.get("label")}

for s in (Label(), Send()):
    register(s)


def _recipe(gate=True):
    return Recipe("rv", steps=[Step("label", "rv_label", inputs={"text": "payload.text"}, gate=gate),
                               Step("send", "rv_send", inputs={"label": "label.label"})],
                  edges=[Edge("label", "send")])


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(examples, "EX_ROOT", tmp_path / "ex")
    monkeypatch.setattr(examples, "PRIVATE_ROOT", tmp_path / "priv")
    monkeypatch.setattr(review, "LOG", tmp_path / "log.jsonl")
    return tmp_path


def _paused(tmp_path, texts, gate=True):
    recipe = _recipe(gate)
    board = Board("rv", "rv", state_dir=tmp_path)
    for i, t in enumerate(texts):
        board.add_item(f"i{i}", {"text": t})
    disp = Dispatcher(recipe, board, Tracer("rv", log_dir=tmp_path, echo=False))
    disp.run()
    return recipe, board, disp


def test_an_edit_at_the_gate_flows_downstream_and_is_learned(store):
    recipe, board, disp = _paused(store, ["refund please"])
    out = review.decide(disp, recipe, "i0", approve=True, holdout_rate=0,
                        verdicts={"label": {"verdict": "edited", "output": {"label": "refunds", "confidence": 1.0}}})
    assert board.context["i0"]["send"] == {"sent": "refunds"}         # downstream used the edit
    assert out["learned"] == {"edited": 1}
    assert examples.load_examples("rv_label")[0]["output"]["label"] == "refunds"


def test_a_rejection_with_a_reason_becomes_a_counterexample(store):
    recipe, board, disp = _paused(store, ["refund please"])
    review.decide(disp, recipe, "i0", approve=False, reason="refunds are not billing",
                  verdicts={"label": {"verdict": "wrong"}})
    assert board.card("i0", "send").status == "skipped"
    rec = examples.load_examples("rv_label")[0]
    assert rec["verdict"] == "rejected" and rec["reason"] == "refunds are not billing"
    with fewshot.force(True):
        assert fewshot.retrieve("rv_label", {"text": "refund please"}) == []   # never shown as right


def test_approving_untouched_confirms_and_holdout_items_stay_apart(store):
    recipe, board, disp = _paused(store, ["a", "b"])
    review.decide(disp, recipe, "i0", approve=True, holdout_rate=0)
    review.decide(disp, recipe, "i1", approve=True, holdout_rate=1)
    assert len(examples.load_examples("rv_label")) == 1
    assert len(examples.load_holdout("rv_label")) == 1
    rates = review.error_rates("rv")
    assert rates == [{"recipe": "rv", "step": "label", "specialist": "rv_label", "reviewed": 2,
                      "right": 2, "edited": 0, "wrong": 0, "error_rate": 0.0}]


def test_an_edit_missing_a_contract_field_is_refused(store):
    recipe, board, disp = _paused(store, ["a"])
    with pytest.raises(ValueError, match="missing"):
        review.decide(disp, recipe, "i0", approve=True,
                      verdicts={"label": {"verdict": "edited", "output": {"label": "x"}}})
    assert board.card("i0", "label").status == "gated"               # nothing applied


def test_a_confidence_gate_holds_only_unsure_items(store):
    recipe, board, _ = _paused(store, ["sure thing", "hmm"],
                               gate={"below": 0.8, "confidence": "label.confidence"})
    assert board.card("i0", "label").status == "done" and board.card("i0", "send").status == "done"
    assert board.card("i1", "label").status == "gated"


def test_a_sample_gate_holds_the_same_items_every_time(store):
    texts = [f"t{i}" for i in range(40)]
    _, b1, _ = _paused(store / "a", texts, gate={"sample": 0.25})
    _, b2, _ = _paused(store / "b", texts, gate={"sample": 0.25})
    held = [c.item_id for c in b1.with_status("gated")]
    assert held == [c.item_id for c in b2.with_status("gated")] and 0 < len(held) < 40


def test_rulebook_lock_history_and_diff(store, monkeypatch):
    monkeypatch.setattr(fewshot, "RULES_DIR", store / "rules")
    monkeypatch.setattr(fewshot, "_RULES_MEM", {})
    golds = [{"input": {"text": f"m{i}"}, "output": {"label": "a" if i % 2 else "b"}} for i in range(9)]
    answers = iter(["1. odd → a", "1. odd → a\n2. even → b"])
    monkeypatch.setattr("engine.core.brain", lambda *a, **k: next(answers))
    inp = {"text": "m"}
    with fewshot.using("rv_label", golds[:8]):
        assert fewshot.rulebook("rv_label", inp)[0] == "1. odd → a"
    with fewshot.using("rv_label", golds):
        assert fewshot.rulebook("rv_label", inp)[0].endswith("even → b")
        assert "+2. even → b" in fewshot.diff("rv_label", inp)
        assert [h["n"] for h in fewshot.history("rv_label", inp)] == [8, 9]
        fewshot.lock("rv_label", inp, rules_text="1. everything → b", by="mike")
        [sl] = fewshot.slots()
        assert sl["specialist"] == "rv_label" and sl["versions"] == 2 and sl["locked"]
        assert fewshot.rulebook("rv_label", inp) == ("1. everything → b", 9)
        fewshot.unlock("rv_label", inp)
        assert fewshot.rulebook("rv_label", inp)[0].endswith("even → b")


def test_validator_policy_gates():
    from engine.core import validate
    errs = lambda r: [f.msg for f in validate(r) if f.level == "error"]
    assert errs(_recipe({"below": 0.8, "confidence": "label.confidence"})) == []
    assert any("doesn't produce" in m for m in errs(_recipe({"below": 0.8, "confidence": "label.certainty"})))
    assert any("between 0 and 1" in m for m in errs(_recipe({"sample": 2})))
    assert any("policy" in m for m in errs(_recipe({"every": 3})))
    class Act(Specialist):
        name = "rv_act"; side_effect = True
        contract = Contract(input={}, output={"ok": object})
        def _run(self, input, config): return {"ok": True}
    register(Act())
    r = Recipe("rv2", steps=[Step("label", "rv_label", inputs={"text": "payload.text"}, gate={"sample": 0.1}),
                             Step("act", "rv_act")], edges=[Edge("label", "act")])
    assert any("doesn't count" in m for m in errs(r))


class Split(Specialist):
    name = "rv_split"
    contract = Contract(input={"text": str}, output={"items": list})
    def _run(self, input, config): return {"items": input["text"].split(";")}


register(Split())


def _each_recipe(each="split.items", inputs=None, gate=False):
    return Recipe("rve", steps=[Step("split", "rv_split", inputs={"text": "payload.text"}),
                                Step("label", "rv_label", each=each, inputs=inputs or {"text": "each"}, gate=gate)],
                  edges=[Edge("split", "label")])


def test_for_each_runs_once_per_element(tmp_path):
    board = Board("rve", "rve", state_dir=tmp_path)
    board.add_item("i0", {"text": "sure a;b;sure c"})
    Dispatcher(_each_recipe(), board, Tracer("rve", log_dir=tmp_path, echo=False)).run()
    out = board.context["i0"]["label"]
    assert out["count"] == 3 and [r["confidence"] for r in out["results"]] == [0.9, 0.4, 0.9]


def test_validator_for_each():
    from engine.core import validate
    errs = lambda r: [f.msg for f in validate(r) if f.level == "error"]
    assert errs(_each_recipe()) == []
    assert any("doesn't produce" in m for m in errs(_each_recipe(each="split.rows")))
    assert any("no step" in m for m in errs(_each_recipe(each="splt.items")))
    r = Recipe("x", steps=[Step("label", "rv_label", inputs={"text": "each"})])
    assert any("set its `each`" in m for m in errs(r))
    r = Recipe("x", steps=[Step("label", "rv_label", each="payload.rows", inputs={"text": "each.body"}),
                           Step("send", "rv_send", inputs={"label": "label.results"})])
    assert errs(r) == []


def test_review_learns_one_example_per_element(store):
    board = Board("rve", "rve", state_dir=store)
    board.add_item("i0", {"text": "a;b"})
    recipe = _each_recipe(gate=True)
    disp = Dispatcher(recipe, board, Tracer("rve", log_dir=store, echo=False))
    disp.run()
    edited = {"results": [{"label": "x", "confidence": 1.0}, {"label": "y", "confidence": 1.0}]}
    review.decide(disp, recipe, "i0", approve=True, holdout_rate=0,
                  verdicts={"label": {"verdict": "edited", "output": edited}})
    got = [(e["input"]["text"], e["output"]["label"]) for e in examples.load_examples("rv_label")]
    assert got == [("a", "x"), ("b", "y")]
