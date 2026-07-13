"""1C — the empirical few-shot policy: block() is gated by a cached per-specialist verdict, and
the verdict is decided by comparing leave-one-out WITH vs WITHOUT few-shot. All pure (no brain)."""

from engine import fewshot, registry
from evals.examples_eval import _fit_verdict, _helps


def test_helps_decision():
    assert _helps(9, 8) is True      # few-shot better  -> keep it on
    assert _helps(8, 8) is True      # tie              -> keep it on (few-shot is the default)
    assert _helps(8, 9) is False     # few-shot worse   -> turn it off (the checker case)


def test_fit_verdict_majority_vote():
    # 2B': vote across samples; ties in the vote keep it on
    assert _fit_verdict([9, 9, 8], [8, 8, 9])["helps"] is True    # 2 of 3 favor few-shot
    assert _fit_verdict([8, 8, 9], [9, 9, 9])["helps"] is False   # only 1 of 3
    assert _fit_verdict([9, 8], [8, 9])["helps"] is True          # 1/2 vote -> tie -> on
    v = _fit_verdict([8, 10], [9, 9])
    assert v["votes"] == "1/2" and v["with_mean"] == 9.0 and v["without_mean"] == 9.0


def test_force_overrides_policy():
    # force(False) makes block() skip regardless of the cached policy
    with fewshot.force(False):
        assert fewshot.block("verify", {"item": "x"}) == ""
        assert fewshot.policy_on("verify") is False
    # force(True) forces it on regardless of the cached policy
    with fewshot.force(True):
        assert fewshot.policy_on("verify") is True
    # outside a force block, we're back to following the cached policy
    assert fewshot._FORCE is None


def test_block_respects_cached_policy(monkeypatch):
    fake = [{"input": {"item": "x"}, "output": {"label": "y"}}]
    monkeypatch.setattr(fewshot, "retrieve", lambda *a, **k: fake)

    monkeypatch.setattr(registry, "fewshot_helps", lambda name: False)
    assert fewshot.block("verify", {"item": "x"}) == ""          # policy off -> nothing injected

    monkeypatch.setattr(registry, "fewshot_helps", lambda name: True)
    out = fewshot.block("verify", {"item": "x"})                 # policy on  -> golds injected
    assert "INPUT" in out and "OUTPUT" in out


def test_registry_policy_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_PATH", tmp_path / "registry.json")
    assert registry.fewshot_helps("brand_new") is True          # unknown defaults to on
    registry.record_fewshot_fit("brand_new", False, {"with": "8/10", "without": "9/10"})
    assert registry.fewshot_helps("brand_new") is False
    assert registry.track_record("brand_new")["fewshot_fit"]["without"] == "9/10"
