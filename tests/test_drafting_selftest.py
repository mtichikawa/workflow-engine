"""3A — harden the drafted-specialist structural self-test. Pure tests for the new checks:
non-empty outputs (the contract passes {field: None}), a measured consistency rate (not a broken
temp-0 equality), and degeneracy. No brain."""

import pytest

from engine.autotest import _consistency, _degenerate, _nonempty


def test_nonempty_catches_null_and_empty():
    assert _nonempty({"label": "bug", "confidence": 0.9}) is True
    assert _nonempty({"label": None}) is False          # contract would pass this; we don't
    assert _nonempty({"label": ""}) is False
    assert _nonempty({"label": []}) is False
    assert _nonempty({}) is False


def test_consistency_is_a_rate():
    assert _consistency([{"y": 1}, {"y": 1}, {"y": 1}]) == 1.0
    assert _consistency([{"y": 1}, {"y": 1}, {"y": 2}]) == pytest.approx(2 / 3)
    assert _consistency([]) == 0.0


def test_degenerate_detects_constant_output():
    assert _degenerate([{"y": 1}, {"y": 1}]) is True     # different inputs, identical output
    assert _degenerate([{"y": 1}, {"y": 2}]) is False
    assert _degenerate([{"y": 1}]) is False              # need >1 to judge
