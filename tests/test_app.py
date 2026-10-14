"""The workbench's API functions end to end: save → run → review queue → decide → quality. No brain."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from engine import app, examples, review, workflows
from engine.core import Contract, Specialist, register


class Tag(Specialist):
    name = "ap_tag"
    contract = Contract(input={"text": str, "tags": list}, output={"label": str, "confidence": float})
    def _run(self, input, config): return {"label": input["tags"][0], "confidence": 0.5}


register(Tag())
RECIPE = {"steps": [{"id": "tag", "specialist": "ap_tag", "inputs": {"text": "payload.text"},
                     "config": {"tags": ["a", "b"]}, "gate": True}], "edges": []}


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(workflows, "DIR", tmp_path / "state/workflows")
    monkeypatch.setattr(examples, "EX_ROOT", tmp_path / "ex")
    monkeypatch.setattr(review, "LOG", tmp_path / "log.jsonl")


def test_save_run_review_decide():
    assert app.check(RECIPE) == {"errors": [], "warnings": []}
    workflows.save("tagger", RECIPE, request="tag it", source={"kind": "pasted"})
    r = app.run_workflow("tagger", {"data": "one\ntwo\n"})
    assert r["items"] == 2
    q = app.review_queue()
    assert len(q) == 2 and q[0]["workflow"] == "tagger" and q[0]["steps"][0]["gate"]
    item = q[0]["item"]
    out = app.decide(r["run"], item, {"approve": True, "verdicts": {
        "tag": {"verdict": "edited", "output": {"label": "b", "confidence": 1.0}}}})
    assert out["learned"] == {"edited": 1}
    assert len(app.review_queue()) == 1
    s = app.run_summary(r["run"])
    assert {i["item"]: i["steps"]["tag"]["status"] for i in s["items"]}[item] == "done"
    assert app.quality()["steps"][0]["edited"] == 1
    assert examples.load_examples("ap_tag", ["wf-tagger"]) and not examples.load_examples("ap_tag", ["baseline"])


def test_check_reports_malformed_and_invalid():
    assert app.check({"steps": [{"id": "x"}]})["errors"][0].startswith("malformed")
    bad = {"steps": [{"id": "tag", "specialist": "ap_tag", "inputs": {"text": "nope.text"}}]}
    assert app.check(bad)["errors"]
