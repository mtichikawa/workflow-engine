"""4B — the tailored-weight retrieval lever: with a tenant scope active, TAILORED_WEIGHT>1 lets a
tenant's exemplar outrank a slightly-more-similar baseline one. Pure — monkeypatches the layered
pool + the active scope layers, no brain."""

from engine import fewshot

_BASE = {"input": {"message": "reset my password please"}, "output": {"reply": "baseline"}}
_TAIL = {"input": {"message": "reset password"}, "output": {"reply": "tenant"}}
_QUERY = {"message": "reset my password please"}   # identical to baseline, superset of tenant


def _wire(monkeypatch):
    # respond is free-form (no config filter), so retrieval isolates the weighting behavior
    monkeypatch.setattr(fewshot.examples, "load_layered",
                        lambda s, layers=None: [(_BASE, "baseline"), (_TAIL, "acme")])
    monkeypatch.setattr(fewshot._scope, "read_layers", lambda: ["baseline", "acme"])


def test_default_weight_prefers_more_similar_baseline(monkeypatch):
    _wire(monkeypatch)
    got = fewshot.retrieve("respond", dict(_QUERY), k=2)
    assert got[0]["output"]["reply"] == "baseline"     # baseline is more content-similar


def test_tailored_weight_boosts_tenant(monkeypatch):
    _wire(monkeypatch)
    with fewshot.tailored_weight(5.0):
        got = fewshot.retrieve("respond", dict(_QUERY), k=2)
    assert got[0]["output"]["reply"] == "tenant"       # boosted above the closer baseline
    assert fewshot.TAILORED_WEIGHT == 1.0              # restored on exit
