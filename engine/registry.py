"""Library-registry — the specialists as a discoverable, quality-tracked catalog.

More than a name→instance map: each specialist has metadata (description, tags,
contract) and a persisted **track-record** (how many times it has run, its latest
eval score). The Composer reads this catalog to select parts — and can prefer ones
with a proven track-record. This is what makes the compounding library tangible.
"""

from __future__ import annotations

import json
from pathlib import Path

from .core import all_specialists

_PATH = Path("state/registry.json")

# Descriptions live here as the catalog's source of truth; a specialist may override
# via its own `description` class attribute (first-class metadata on the specialist).
DESCRIPTIONS = {
    "fetch": "pull items from an external source (github/github_pr/hn). config: source, params.",
    "classify": "assign an item to one of N categories. config: categories (list), criteria.",
    "rank": "score an item 0..1 on a dimension. config: scoring.",
    "verify": "check a subject/claim against a standard. config: standard.",
    "act": "stage an action to a target (github/file), behind a gate. config: target, mode.",
    "route": "[domain] route an issue to a component and decide escalation. config: components.",
    "respond": "[domain] draft a first reply to an issue or message. config: tone.",
    "write": "[domain] draft a short post from a topic + sources.",
    "review": "[domain] review a PR/diff: findings, risk, a reviewer comment. config: checklist.",
}


# ---- track-record (persisted) ------------------------------------------
def _load() -> dict:
    return json.loads(_PATH.read_text()) if _PATH.exists() else {}


def _save(d: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(d, indent=2))


def record_run(name: str, n: int = 1) -> None:
    d = _load()
    d.setdefault(name, {})["runs"] = d.get(name, {}).get("runs", 0) + n
    _save(d)


def record_eval(name: str, score: float, kind: str) -> None:
    d = _load()
    r = d.setdefault(name, {})
    r["eval_score"] = round(score, 3)
    r["eval_kind"] = kind
    _save(d)


def record_fewshot_fit(name: str, helps: bool, detail: dict | None = None) -> None:
    """Cache the train-time verdict: does few-shot improve THIS specialist's eval? (learning-loop
    1C). Written by `engine fit`; read by fewshot.block(). Replaces the old hardcoded per-name skip."""
    d = _load()
    r = d.setdefault(name, {})
    r["fewshot_helps"] = bool(helps)
    if detail is not None:
        r["fewshot_fit"] = detail
    _save(d)


def fewshot_helps(name: str) -> bool:
    """Policy read by fewshot.block(). Unknown -> True: most specialists are mappers that benefit;
    the empirical fit check (`engine fit`) flips checkers to False from data, not from a hardcode."""
    return _load().get(name, {}).get("fewshot_helps", True)


def track_record(name: str) -> dict:
    return _load().get(name, {})


def mark_provisional(name: str) -> None:
    d = _load()
    d.setdefault(name, {})["provisional"] = True
    _save(d)


def is_provisional(name: str) -> bool:
    return bool(_load().get(name, {}).get("provisional"))


def clear_provisional(name: str) -> None:
    d = _load()
    if name in d:
        d[name]["provisional"] = False
        _save(d)


def promote(name: str, min_eval: float = 0.8, min_examples: int = 4) -> bool:
    """A provisional specialist earns trust once its eval clears the bar on enough examples.
    Returns True if it was promoted."""
    from .fewshot import load as load_examples
    tr = track_record(name)
    score = tr.get("eval_score")
    n = len(load_examples(name))
    if score is not None and score >= min_eval and n >= min_examples:
        clear_provisional(name)
        return True
    return False


# ---- catalog ------------------------------------------------------------
def describe(name: str, spec) -> str:
    return getattr(spec, "description", "") or DESCRIPTIONS.get(name, "")


def catalog() -> list[dict]:
    out = []
    for name, spec in sorted(all_specialists().items()):
        tr = track_record(name)
        out.append({
            "name": name, "kind": spec.kind, "does": describe(name, spec),
            "tags": list(getattr(spec, "tags", ())),
            "input": list(spec.contract.input), "output": list(spec.contract.output),
            "track_record": {"runs": tr.get("runs", 0), "eval": tr.get("eval_score")},
        })
    return out
