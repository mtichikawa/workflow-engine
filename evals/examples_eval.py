"""Examples-as-eval — score a specialist against its own curated golds, leave-one-out.

For each gold: inject the OTHER golds as few-shot and test on the held-out one — never eval
on an injected example (no circularity). Works from a handful of golds and strengthens as
they accumulate. It measures whether few-shot on the curated examples reproduces the human's
judgment. (Requires the specialist to actually inject few-shot; the capability specialists
and drafted specialists do.)
"""

from __future__ import annotations

from engine import fewshot
from engine.core import all_specialists, get


def _num(x, d=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


# how a specialist's output is judged against a gold output
MATCH = {
    "classify": lambda o, g: o.get("label") == g.get("label"),
    "route": lambda o, g: o.get("component") == g.get("component"),
    "verify": lambda o, g: o.get("verdict") == g.get("verdict"),
    "rank": lambda o, g: abs(_num(o.get("score")) - _num(g.get("score"))) <= 0.25,
    "escalate_policy": lambda o, g: str(o.get("decision", "")).lower().startswith(
        str(g.get("decision", "")).lower()[:4]),
}

MIN_GOLDS = 3


def loo(specialist: str):
    """Leave-one-out score over a specialist's golds. Returns (passed, total) or None."""
    match = MATCH.get(specialist)
    golds = fewshot.load(specialist)
    if not match or specialist not in all_specialists() or len(golds) < MIN_GOLDS:
        return None
    passed = 0
    for i, held in enumerate(golds):
        subset = golds[:i] + golds[i + 1:]
        with fewshot.using(specialist, subset):
            out = get(specialist).run(held["input"], {})
        passed += bool(match(out, held.get("output", {})))
    return passed, len(golds)


def run_all() -> list[tuple]:
    """(specialist, passed, total) for every specialist with enough golds + a matcher."""
    rows = []
    for name in sorted(MATCH):
        res = loo(name)
        if res:
            rows.append((name, res[0], res[1]))
    return rows


# ---- 1C: empirical, per-specialist "does few-shot help?" (replaces hardcoding checkers) --------
def _helps(with_passed: int, without_passed: int) -> bool:
    """Few-shot 'helps' iff it scores at least as well as no few-shot. Ties keep it ON — few-shot
    is the default, and a tie today can become a win as golds accumulate."""
    return with_passed >= without_passed


def loo_with(specialist: str, on: bool):
    """Leave-one-out with few-shot FORCED on or off (bypasses the cached policy). (passed, total)."""
    match = MATCH.get(specialist)
    golds = fewshot.load(specialist)
    if not match or specialist not in all_specialists() or len(golds) < MIN_GOLDS:
        return None
    passed = 0
    for i, held in enumerate(golds):
        subset = golds[:i] + golds[i + 1:]
        with fewshot.force(on), fewshot.using(specialist, subset):
            out = get(specialist).run(held["input"], {})
        passed += bool(match(out, held.get("output", {})))
    return passed, len(golds)


def _fit_verdict(with_scores: list[int], without_scores: list[int]) -> dict:
    """2B': aggregate K samples. The CLI brain is non-deterministic (no temp/seed), so a single
    pass is noisy — vote across samples instead. 'helps' iff few-shot wins-or-ties in a MAJORITY of
    samples (ties keep it on: few-shot is the default). Carries means + raw scores so noise shows."""
    votes = [_helps(w, o) for w, o in zip(with_scores, without_scores)]
    helps = sum(votes) * 2 >= len(votes)
    mw = sum(with_scores) / len(with_scores)
    mo = sum(without_scores) / len(without_scores)
    return {"helps": helps, "votes": f"{sum(votes)}/{len(votes)}",
            "with_mean": round(mw, 2), "without_mean": round(mo, 2),
            "with": with_scores, "without": without_scores}


def fewshot_fit(specialist: str, samples: int = 1, cache: bool = True):
    """Does few-shot improve this specialist's eval? Run LOO with AND without few-shot `samples`
    times each, majority-vote the verdict, and (by default) cache it. The general, data-driven
    replacement for the old per-name 'checkers skip few-shot' hardcode — mapper-vs-checker EMERGES,
    and multi-sampling makes the verdict robust to the CLI brain's non-determinism (2B')."""
    total = None
    with_scores: list[int] = []
    without_scores: list[int] = []
    for _ in range(max(1, samples)):
        on = loo_with(specialist, True)
        off = loo_with(specialist, False)
        if not on or not off:
            return None
        total = on[1]
        with_scores.append(on[0])
        without_scores.append(off[0])
    v = _fit_verdict(with_scores, without_scores)
    detail = {"n": total, "samples": len(with_scores), **v}
    if cache:
        from engine import registry
        registry.record_fewshot_fit(specialist, v["helps"], detail)
    return detail


def fit_all(samples: int = 1, cache: bool = True) -> list[tuple]:
    """(specialist, detail) for every specialist with a matcher + enough golds."""
    rows = []
    for name in sorted(MATCH):
        d = fewshot_fit(name, samples=samples, cache=cache)
        if d:
            rows.append((name, d))
    return rows
