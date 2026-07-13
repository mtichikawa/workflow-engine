"""Eval suite — one eval per specialist.

Blueprint rule (enforced by `engine eval`): EVERY specialist ships with an eval.
Judgment specialists get accuracy evals (labeled right answers); generative and
mechanical ones get validity/smoke checks (valid, non-empty, contract-satisfying).

    python -m engine.cli eval            # run all, report scores + any missing eval
    python -m engine.cli eval classify   # one specialist
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.core import all_specialists, get


@dataclass
class EvalResult:
    specialist: str
    kind: str                       # "accuracy" | "smoke"
    passed: int
    total: int
    detail: list = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.passed / self.total if self.total else 0.0


def _accuracy(spec_name, kind, config, cases, check) -> EvalResult:
    spec = get(spec_name)
    passed, detail = 0, []
    for inp, expected in cases:
        out = spec.run(inp, config)
        ok = bool(check(out, expected))
        passed += ok
        detail.append((inp, out, expected, ok))
    return EvalResult(spec_name, kind, passed, len(cases), detail)


# ---- classify -----------------------------------------------------------
_CATS = ["bug", "feature", "question", "spam"]
_CLASSIFY = [
    ({"item": {"title": "Crash on startup", "body": "NPE on launch."}}, "bug"),
    ({"item": {"title": "Add dark mode", "body": "want a dark theme"}}, "feature"),
    ({"item": {"title": "How do I reset my password?"}}, "question"),
    ({"item": {"title": "BUY CHEAP FOLLOWERS", "body": "sketchy.example"}}, "spam"),
    ({"item": {"title": "Export to CSV downloads 0-byte file"}}, "bug"),
    ({"item": {"title": "Support webhooks for events"}}, "feature"),
]

def eval_classify():
    return _accuracy("classify", "accuracy",
                     {"categories": _CATS, "criteria": "issue type"},
                     _CLASSIFY, lambda o, e: o["label"] == e)


# ---- rank (pairwise: the more-urgent item must score >= the less-urgent) --
_RANK_SCORING = "urgency: outage or security > broken feature > cosmetic/nice-to-have"
_RANK_PAIRS = [
    ({"title": "Production down, 500 on every request"}, {"title": "Typo in the README"}),
    ({"title": "Auth bypass lets anyone read others' data"}, {"title": "Add a dark theme someday"}),
    ({"title": "Payments double-charging customers"}, {"title": "Button color is slightly off"}),
]

def eval_rank():
    spec = get("rank")
    cfg = {"scoring": _RANK_SCORING}
    passed, detail = 0, []
    for hi, lo in _RANK_PAIRS:
        sh = spec.run({"item": hi}, cfg)["score"]
        sl = spec.run({"item": lo}, cfg)["score"]
        ok = sh >= sl
        passed += ok
        detail.append(((hi["title"], sh), (lo["title"], sl), "hi>=lo", ok))
    return EvalResult("rank", "accuracy", passed, len(_RANK_PAIRS), detail)


# ---- verify -------------------------------------------------------------
_VERIFY = [
    ({"subject": "The sum: 2 + 2 = 5", "standard": "the arithmetic is correct"}, "fail"),
    ({"subject": "Paris is the capital of France.", "standard": "the statement is factually correct"}, "pass"),
    ({"subject": "Thanks — could you share your version and a repro?",
      "standard": "a support reply that is relevant and asks for missing info"}, "pass"),
]

def eval_verify():
    return _accuracy("verify", "accuracy", {}, _VERIFY, lambda o, e: o["verdict"] == e)


# ---- route --------------------------------------------------------------
_COMPONENTS = ["core", "api", "docs", "build", "ui", "auth", "other"]
_ROUTE = [
    ({"item": {"title": "Login fails with valid credentials", "body": "OAuth token rejected"}}, "auth"),
    ({"item": {"title": "Typo in the installation guide"}}, "docs"),
    ({"item": {"title": "npm run build fails on CI"}}, "build"),
]

def eval_route():
    return _accuracy("route", "accuracy", {"components": _COMPONENTS},
                     _ROUTE, lambda o, e: o["component"] == e)


# ---- smoke checks (generative / mechanical) -----------------------------
def _smoke(spec_name, inp, config, field_ok) -> EvalResult:
    out = get(spec_name).run(inp, config)
    ok = bool(field_ok(out))
    return EvalResult(spec_name, "smoke", int(ok), 1, [(inp, out, "valid", ok)])

def eval_respond():
    return _smoke("respond", {"item": {"title": "App crashes", "body": "on login"}},
                  {"tone": "helpful"}, lambda o: len(o["reply"]) > 20)

def eval_write():
    return _smoke("write", {"topic": "why tests matter", "sources": [], "brief": "no hype"},
                  {}, lambda o: 20 < len(o["post"]) < 1200)

def eval_review():
    pr = {"title": "Add retry to http client", "body": "adds 3 retries", "diff": "+ for i in range(3): call()"}
    return _smoke("review", {"item": pr}, {"checklist": "correctness, tests"},
                  lambda o: o["risk"] in ("low", "medium", "high"))

def eval_fetch():
    return _smoke("fetch", {"source": "hn", "params": {"limit": 2}}, {},
                  lambda o: len(o["items"]) >= 1)

def eval_act():
    return _smoke("act", {"target": "file", "payload": {"content": "hi", "name": "eval.txt"},
                          "mode": "staged"}, {"out_dir": "output"}, lambda o: o["status"] == "staged")


EVALS = {
    "classify": eval_classify, "rank": eval_rank, "verify": eval_verify, "route": eval_route,
    "respond": eval_respond, "write": eval_write, "review": eval_review,
    "fetch": eval_fetch, "act": eval_act,
}


def missing_evals() -> list[str]:
    """The convention, enforced: every TRUSTED specialist must have an eval. Provisional
    (drafted, not-yet-promoted) specialists are exempt by design — they earn their eval when
    they earn trust (draft → validate → track-record → promote), so they aren't a violation."""
    from engine.registry import is_provisional
    return sorted(n for n in set(all_specialists()) - set(EVALS) if not is_provisional(n))


def provisional_without_eval() -> list[str]:
    """Provisional specialists lacking an eval — expected, reported separately (not a violation)."""
    from engine.registry import is_provisional
    return sorted(n for n in set(all_specialists()) - set(EVALS) if is_provisional(n))


def run(names=None) -> list[EvalResult]:
    names = names or list(EVALS)
    return [EVALS[n]() for n in names if n in EVALS]
