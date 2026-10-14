"""Saved workflows (versions, diff, run) and input sources — deterministic, no brain."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import pytest

from engine import inputs, workflows
from engine.core import Contract, Edge, Recipe, Specialist, Step, register


class Upper(Specialist):
    name = "wf_upper"
    contract = Contract(input={"text": str}, output={"text": str})
    def _run(self, input, config): return {"text": input["text"].upper()}


register(Upper())
RECIPE = Recipe("x", steps=[Step("up", "wf_upper", inputs={"text": "payload.text"})])


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(workflows, "DIR", tmp_path / "wf")


def test_save_versions_and_diff():
    assert workflows.save("shout", RECIPE, request="make it loud") == 1
    assert workflows.save("shout", RECIPE) == 1                      # unchanged: no new version
    d = workflows.to_dict(RECIPE)
    d["steps"].append({"id": "up2", "specialist": "wf_upper", "inputs": {"text": "up.text"}})
    d["edges"] = [{"from": "up", "to": "up2"}]
    assert workflows.save("shout", d, note="twice") == 2
    r, meta = workflows.load("shout")
    assert [s.id for s in r.steps] == ["up", "up2"] and meta["request"] == "make it loud"
    assert '"id": "up2"' in workflows.diff("shout", 1, 2)
    assert workflows.load("shout", 1)[0].step_ids() == ["up"]


def test_an_invalid_workflow_is_not_saved():
    bad = Recipe("x", steps=[Step("up", "wf_upper", inputs={"text": "nope.text"})])
    bad.steps[0].inputs = {"text": "up2.text"}
    bad.steps.append(Step("up2", "wf_upper", inputs={"text": "payload.text"}))
    bad.edges = [Edge("up", "up2")]
    with pytest.raises(ValueError, match="doesn't validate"):
        workflows.save("bad", bad)
    assert workflows.versions("bad") == []
    with pytest.raises(ValueError, match="lowercase"):
        workflows.save("Bad Name", RECIPE)


def test_run_on_csv_rows(tmp_path):
    workflows.save("shout", RECIPE, source={"kind": "csv"})
    items = inputs.csv_rows(None, data="id,text\n7,hi\n8,there\n")
    assert [i for i, _ in items] == ["7", "8"] and items[0][1]["text"] == "id: 7\ntext: hi"
    run_id = workflows.run("shout", items)
    from engine.core import Board
    board = Board.load(run_id)
    assert board.context["7"]["up"]["text"] == "ID: 7\nTEXT: HI"
    assert workflows.runs("shout")[0]["items"] == 2
    assert workflows.all_workflows()[0]["runs"] == 1


def test_sources(tmp_path):
    assert len(inputs.pasted("a\n\nb\nc", split="line")) == 3
    assert [p["text"] for _, p in inputs.pasted("a\n\nb\nc", split="block")] == ["a", "b\nc"]
    assert inputs.csv_rows(None, data="name\tnote\nx\ty\n")[0][1]["note"] == "y"   # tab-separated
    assert inputs.jsonl(None, data='{"id": 3, "text": "t"}\n')[0] == ("3", {"id": 3, "text": "t"})
    d = tmp_path / "in"; d.mkdir()
    (d / "a.txt").write_text("hello"); (d / "b.png").write_bytes(b"\x89PNG"); (d / "c.bin").write_bytes(b"x")
    got = dict(inputs.folder(d))
    assert got["a.txt"]["text"] == "hello" and got["b.png"]["files"] and "c.bin" not in got
    seen = tmp_path / "seen.json"
    assert len(inputs.new_only(list(got.items()), seen)) == 2
    assert inputs.new_only(list(got.items()), seen) == []
    (d / "a.txt").write_text("changed")
    assert [i for i, _ in inputs.new_only(inputs.folder(d), seen)] == ["a.txt"]   # changed content is new
