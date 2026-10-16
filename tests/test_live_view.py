"""The live demo's view of its case (engine/live/view.py) and the composer's progress reports.

Deterministic: the graph and box details come from the recipe and the recorded run; the composer test stubs
the model with a bad draft then a good one — no brain.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import composer
from engine.live import care_intake as case
from engine.live import view

case.load()
RUN = {s["id"]: s for s in json.loads(case.TAPE.with_name("tape-run.json").read_text())["steps"]}


def test_graph_names_every_box_and_column():
    g = view.graph(case)
    ids = {n["id"] for n in g["nodes"]}
    assert ids == {"IN"} | {s.id for s in case.RECIPE.steps}          # no separate OUT box
    assert len(g["phases"]) == max(n["col"] for n in g["nodes"]) + 1
    by = {n["id"]: n for n in g["nodes"]}
    assert by["triage"]["title"] == case.LABELS["triage"] and by["packet"]["kind"] == "gate"
    assert all(w[0] in ids and w[2] in ids for w in g["wires"])


def test_reader_method_is_known_before_the_run():
    """The fax is a scan (the model reads it); the intake PDF has a text layer (plain code) — before any run."""
    by = {n["id"]: n for n in view.graph(case)["nodes"]}
    assert by["read_referral"]["sub"] == "read_document · model"
    assert by["read_intake"]["sub"] == "read_document · code"


def test_static_and_recorded_graphs_differ_only_in_run_detail():
    static, recorded = view.graph(case), view.graph(case, RUN)
    assert static["wires"] == recorded["wires"]
    for a, b in zip(static["nodes"], recorded["nodes"]):
        assert a["sub"] == b["sub"]
        assert b["detail"][:len(a["detail"])] == a["detail"]                # does / specialist first, then the run


def test_step_detail_from_a_recorded_step():
    d = view.step_detail(case, "triage", RUN["triage"]["output"], RUN["triage"]["seconds"])
    rows = dict(d["detail"])
    assert d["sub"] == "classify · model"
    assert rows["result"].startswith("medical") and rows["why"] and rows["time"].endswith(" s")


def test_findings_grow_as_steps_finish():
    out = {sid: r["output"] for sid, r in RUN.items()}
    assert view.findings({}) == []
    early = view.findings({"triage": out["triage"]})
    assert [f["step"] for f in early] == ["triage"]
    assert {f["step"] for f in view.findings(out)} >= {"triage", "identity", "coverage", "fields", "claim", "reply_check"}


def test_an_unreadable_field_is_not_called_missing():
    """The card reader marks what it can't make out ([?]); the finding says so instead of "no document gives it"."""
    fields = {"fields": {"member_id": {"value": None, "source": "insurance card", "unreadable": "DM[?]41827730"},
                         "sex": {"value": None, "source": None}}, "missing": ["member_id", "sex"]}
    texts = [f["text"] for f in view.findings({"fields": fields})]
    assert texts == ["Part of the member ID on the insurance card can't be read (DM[?]41827730), so a person checks it.",
                     "The claim needs the patient's sex, and no document gives it."]


def test_composer_reports_each_stage(monkeypatch):
    bad = {"steps": [{"id": "a", "specialist": "classify", "config": {"categories": ["x", "y"], "criteria": "c"},
                      "inputs": {"item": "payload.text"}}], "edges": [{"from": "a", "to": "nowhere"}]}
    good = {"steps": [{"id": "a", "specialist": "classify", "config": {"categories": ["x", "y"], "criteria": "c"},
                       "inputs": {"item": "payload.text"}}]}
    answers = iter([bad, good])
    monkeypatch.setattr(composer, "brain_json", lambda prompt: next(answers))
    events = []
    res = composer.compose("sort these", progress=events.append)
    assert [e["stage"] for e in events] == ["draft", "invalid", "repair", "valid"]
    assert events[1]["errors"] and all(not e.startswith("[") for e in events[1]["errors"])
    assert events[3] == {"stage": "valid", "attempt": 2, "steps": 1} and res["runnable"]
