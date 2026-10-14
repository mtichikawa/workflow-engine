"""The rulebook (learning-loop 5A): learned per workflow, never shared across workflows or tenants."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine.core
from engine import fewshot


def _golds(categories, n, label):
    cfg = {"categories": categories, "criteria": "c"}
    return [{"input": {"item": f"message {i}", **cfg}, "output": {"label": label, "reasoning": "r"}}
            for i in range(n)]


def _call(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(fewshot, "RULES_DIR", tmp_path)
    monkeypatch.setattr(fewshot, "_RULES_MEM", {})
    monkeypatch.setattr(engine.core, "brain", lambda prompt, *a, **k: seen.append(prompt) or "1. RULE")
    return seen


def test_rulebook_is_written_from_this_workflows_corrections_only(monkeypatch, tmp_path):
    seen = _call(monkeypatch, tmp_path)
    a = _golds(["x", "y"], 10, "x")
    b = _golds(["bug", "spam"], 10, "spam")                      # another workflow's config
    with fewshot.using("classify", a + b):
        book, n = fewshot.rulebook("classify", {"item": "hi", "categories": ["x", "y"], "criteria": "c"})
    assert book == "1. RULE" and n == 10
    assert '"label": "x"' in seen[0] and "spam" not in seen[0]   # B's corrections never reach A's rulebook


def test_no_rulebook_below_the_minimum_and_free_form_never(monkeypatch, tmp_path):
    seen = _call(monkeypatch, tmp_path)
    with fewshot.using("classify", _golds(["x", "y"], fewshot.RULES_MIN - 1, "x")):
        assert fewshot.rulebook("classify", {"item": "hi", "categories": ["x", "y"], "criteria": "c"})[0] == ""
    with fewshot.using("respond", _golds(["x"], 20, "x")):
        assert fewshot.rulebook("respond", {"item": "hi"})[0] == ""
    assert seen == []


def test_induced_once_then_cached_until_the_corrections_change(monkeypatch, tmp_path):
    seen = _call(monkeypatch, tmp_path)
    inp = {"item": "hi", "categories": ["x", "y"], "criteria": "c"}
    golds = _golds(["x", "y"], 10, "x")
    with fewshot.using("classify", golds):
        fewshot.rulebook("classify", inp)
        fewshot.rulebook("classify", inp)
    assert len(seen) == 1
    with fewshot.using("classify", golds + _golds(["x", "y"], 1, "y")):
        fewshot.rulebook("classify", inp)
    assert len(seen) == 2                                         # a new correction -> a new rulebook


def test_switch_off_restores_examples_only(monkeypatch, tmp_path):
    _call(monkeypatch, tmp_path)
    with fewshot.rules(False), fewshot.using("classify", _golds(["x", "y"], 10, "x")):
        assert fewshot.rulebook("classify", {"item": "hi", "categories": ["x", "y"], "criteria": "c"})[0] == ""
