"""Few-shot injection — a specialist reads its curated golds at run time.

Retrieval, not drawers (learning-loop.md §3): keep ONE example pool per specialist and
inject the few most SIMILAR to the current input — never a blanket dump of everything (that
would overfit a universal specialist to one task). If nothing is similar, inject nothing and
fall back to the general skill. Similarity here is cheap and dependency-free (token overlap);
swap in embeddings later without touching callers.

Rulebook (learning-loop 5A): six similar examples teach a convention poorly when it hinges on
something the examples don't share words with (who is writing, which rule wins when two apply). So
once a workflow has RULES_MIN corrections for a config-keyed specialist, the brain reads ALL of them
once and writes the rules they imply — the notes a new hire writes after being corrected — and those
rules ride ahead of the retrieved examples. Same scope as the examples (same specialist, same config,
same tenant chain); cached until the corrections change; derived only from the golds, never edited.
"""

from __future__ import annotations

import contextvars
import difflib
import hashlib
import json
import re
import threading
import time
from pathlib import Path

from . import examples

MIN_SIM = 0.05        # below this, a gold isn't "similar enough" to inject (fall back to the skill)


# Retrieval must rank on the WORK-ITEM CONTENT, not the recipe config. Config fields (tone,
# categories, criteria, scoring, standard, components, brief, …) are constant across a
# specialist's exemplars, so they carry no discriminating signal — and worse, a config field
# that differs BY LAYER (e.g. each tenant's `tone`) biases retrieval toward whichever layer's
# config matches the query, drowning out content. So similarity compares only the content
# fields. (Found via a RESPOND coverage test: `tone` alone pinned every retrieval to the active
# tenant 6/6, making the fallback signal meaningless for voice specialists.)
CONTENT_KEYS = ("item", "subject", "topic", "message", "text", "content", "body")

# 1A — config-agnostic vs config-keyed exemplars (learning-loop.md, "The 3-layer model").
# A CONFIG-KEYED specialist's OUTPUT is drawn from its config vocabulary (classify -> a label from
# config.categories; route -> a component), so an exemplar only demonstrates the config it was written
# for. Injecting one from a DIFFERENT config (e.g. triage's categories into a content classify call)
# would show a label that isn't even in the current vocabulary. FREE-FORM specialists (respond/write)
# output craft that transfers across configs, so their exemplars inject freely. Hence: config-keyed
# retrieval is gated to same-config exemplars; free-form retrieval is not.
FREE_FORM_OUTPUT = {"respond", "write"}


def _config_key(x) -> str:
    """Stable signature of an input's non-content (config-knob) fields."""
    if not isinstance(x, dict):
        return ""
    cfg = {k: v for k, v in x.items() if k not in CONTENT_KEYS}
    return json.dumps(cfg, sort_keys=True, default=str)


def _content(x):
    """The content-bearing part of an input, for similarity — the work item, not the config."""
    if isinstance(x, dict):
        picked = {k: v for k, v in x.items() if k in CONTENT_KEYS}
        return picked or x                              # fall back to the whole input if none match
    return x


def _flatten(x) -> str:
    if isinstance(x, dict):
        return " ".join(_flatten(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return " ".join(_flatten(v) for v in x)
    return str(x)


def _tokens(x) -> set:
    return set(re.findall(r"[a-z0-9]+", _flatten(x).lower()))


def _similarity(a, b) -> float:
    ta, tb = _tokens(_content(a)), _tokens(_content(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)                 # Jaccard, on content only


def load(specialist: str) -> list[dict]:
    """Golds for a specialist across the active scope chain (baseline + tenant)."""
    return examples.load_examples(specialist)


# Eval switches are ContextVars, not globals: parallel evals each hold out a different example, and
# the dispatcher already copies the caller's context into its worker threads (as it does for scope).
_OVERRIDE: contextvars.ContextVar[dict] = contextvars.ContextVar("fewshot_override", default={})
_FORCE: contextvars.ContextVar = contextvars.ContextVar("fewshot_force", default=None)


class _Switch:
    """Set a ContextVar for the duration of a `with` block."""
    var: contextvars.ContextVar

    def __enter__(self):
        self._tok = self.var.set(self._value())

    def __exit__(self, *a):
        self.var.reset(self._tok)


class using(_Switch):
    """Temporarily inject a specific example set (for leave-one-out / held-out eval)."""
    var = _OVERRIDE

    def __init__(self, specialist: str, examples: list):
        self.specialist, self.examples = specialist, examples

    def _value(self):
        return {**_OVERRIDE.get(), self.specialist: self.examples}


class force(_Switch):
    """Force few-shot on/off regardless of the cached policy — used ONLY by evals, so the
    'with vs without few-shot' comparison isn't short-circuited by the policy it's computing (1C)."""
    var = _FORCE

    def __init__(self, on: bool):
        self.on = on

    def _value(self):
        return self.on


def policy_on(specialist: str) -> bool:
    """Should block() inject for this specialist? A `force` context overrides the cached policy."""
    if _FORCE.get() is not None:
        return _FORCE.get()
    from . import registry            # lazy import: avoid a module cycle
    return registry.fewshot_helps(specialist)


TAILORED_WEIGHT = 1.0   # 4B: >1.0 multiplies a tailored-layer exemplar's similarity so it can outrank
                        # a slightly-more-similar baseline one (for same-domain tenant sets, where pure
                        # content similarity under-weights the tenant's own corrections). 1.0 = no change.


class tailored_weight:
    """Scoped override of TAILORED_WEIGHT (a recipe/tenant can dial how hard tailored beats baseline)."""

    def __init__(self, w: float):
        self.w = w

    def __enter__(self):
        global TAILORED_WEIGHT
        self._prev = TAILORED_WEIGHT
        TAILORED_WEIGHT = self.w

    def __exit__(self, *a):
        global TAILORED_WEIGHT
        TAILORED_WEIGHT = self._prev


def _pool(specialist: str, current_input, rejected: bool = False) -> list[tuple[dict, str | None]]:
    """The golds this call may learn from: [(record, layer)] — same config for config-keyed specialists.
    Records a reviewer REJECTED are counterexamples: never retrieved as examples of what's right (they
    feed the rulebook as "wrong, because…" instead); `rejected=True` returns only those."""
    ov = _OVERRIDE.get().get(specialist)
    if ov is not None:
        pool = [(e, None) for e in ov]               # eval override: one layer, no weighting
    else:
        pool = examples.load_layered(specialist)     # [(record, layer)] across the active read chain
    if pool and specialist not in FREE_FORM_OUTPUT:  # 1A: config-keyed -> only same-config exemplars
        ck = _config_key(current_input)
        pool = [(e, lay) for e, lay in pool if _config_key(e.get("input")) == ck]
    return [(e, lay) for e, lay in pool if (e.get("verdict") == "rejected") == rejected]


def retrieve(specialist: str, current_input, k: int = 6) -> list[dict]:
    """The k golds most similar to the current input (most-similar first)."""
    pool = _pool(specialist, current_input)
    if not pool:
        return []
    layers = _scope.read_layers()
    tenant = layers[-1] if len(layers) > 1 else None  # 4B: the tailored layer, if a tenant is active
    scored = []
    for e, lay in pool:
        s = _similarity(e.get("input"), current_input)
        if tenant is not None and lay == tenant and TAILORED_WEIGHT != 1.0:
            s *= TAILORED_WEIGHT                       # boost the tenant's own exemplars
        scored.append((e, s))
    relevant = [(e, s) for e, s in scored if s >= MIN_SIM]     # nothing similar -> inject nothing
    relevant.sort(key=lambda es: es[1], reverse=True)
    return [e for e, _ in relevant[:k]]


from . import scope as _scope

# Below this fraction of tailored examples in the injected slots, a card is flagged. The RAW
# ratio is always recorded (more data); this is only the default flag threshold, tunable.
THIN_COVERAGE = 0.5


def coverage(specialist: str, current_input, k: int = 6) -> dict | None:
    """The layer split (tailored vs baseline) of the slots that WOULD be injected for this input.
    Records the raw ratio always; flags derive from it. Returns None when no tenant scope is
    active (nothing tailored is possible), so it's a uniform no-op outside a tenant."""
    layers = _scope.read_layers()
    if len(layers) < 2:                                   # baseline-only: no tailored layer to miss
        return None
    tenant = layers[-1]
    tagged = examples.load_layered(specialist)            # [(record, layer)]
    if not tagged:
        return None                                        # this specialist uses no few-shot — N/A
    scored = [(rec, lay, _similarity(rec.get("input"), current_input)) for rec, lay in tagged]
    picked = sorted((t for t in scored if t[2] >= MIN_SIM), key=lambda t: t[2], reverse=True)[:k]
    total = len(picked)
    n_tail = sum(1 for _, lay, _ in picked if lay == tenant)
    ratio = (n_tail / total) if total else 0.0
    flag = None
    if ratio == 0.0:
        flag = "no-coverage"                              # tailored layer exists, nothing tailored got in
    elif ratio < THIN_COVERAGE:
        flag = "thin-coverage"                            # baseline out-populated the slots
    return {"has_tailored": True, "tenant": tenant, "tailored": n_tail,
            "baseline": total - n_tail, "total": total, "ratio": round(ratio, 3), "flag": flag}


# ---- 5A: the rulebook --------------------------------------------------------------
RULES_MIN = 8                         # fewer corrections than this are too few to generalize from
RULES_DIR = Path("state/rulebooks")   # derived and cached — regenerated whenever the golds change
_RULES_ON: contextvars.ContextVar = contextvars.ContextVar("fewshot_rules", default=True)
_RULES_LOCK = threading.Lock()
_KEY_LOCKS: dict[str, threading.Lock] = {}     # one per pool: the same pool is induced once, others in parallel
_RULES_MEM: dict[str, str] = {}
_NOT_A_DECISION = ("reasoning", "confidence")


class rules(_Switch):
    """Turn the rulebook on/off for a scope — evals compare examples-only against rulebook + examples."""
    var = _RULES_ON

    def __init__(self, on: bool):
        self.on = on

    def _value(self):
        return self.on


def slot(specialist: str, current_input) -> str:
    """Which rulebook a call belongs to: this specialist, this workflow's config, this tenant chain.
    Versions, locks and diffs are kept per slot."""
    from . import scope as _sc
    task = {k: v for k, v in (current_input or {}).items() if k not in CONTENT_KEYS}
    return hashlib.sha256(json.dumps([specialist, task, _sc.read_layers()], sort_keys=True,
                                     default=str).encode()).hexdigest()[:16]


def _slot_file(kind: str, sl: str) -> Path:
    return RULES_DIR / kind / f"{sl}.json{'l' if kind == 'history' else ''}"


# Every function below takes a slot id, or (specialist, current_input) to name the slot.
def _sl(spec_or_slot: str, current_input=None) -> str:
    return spec_or_slot if current_input is None else slot(spec_or_slot, current_input)


def history(spec_or_slot: str, current_input=None) -> list[dict]:
    """Every rulebook version written for this slot, oldest first: {created, n, rejected, rules, …}."""
    p = _slot_file("history", _sl(spec_or_slot, current_input))
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def diff(spec_or_slot: str, current_input=None, a: int = -2, b: int = -1) -> str:
    """What changed between two rulebook versions (default: the last two), as a unified diff."""
    h = history(spec_or_slot, current_input)
    if len(h) < 2:
        return ""
    va, vb = h[a], h[b]
    return "\n".join(difflib.unified_diff(va["rules"].splitlines(), vb["rules"].splitlines(),
                                           f"{va['n']} corrections", f"{vb['n']} corrections", lineterm=""))


def locked(spec_or_slot: str, current_input=None) -> dict | None:
    p = _slot_file("locked", _sl(spec_or_slot, current_input))
    return json.loads(p.read_text()) if p.exists() else None


def lock(spec_or_slot: str, current_input=None, rules_text: str = "", by: str = "") -> None:
    """A person fixes the rulebook: these rules are used as written until unlocked, whatever the
    corrections say. (The corrections still accumulate, and the 6 closest still ride along.)"""
    if not rules_text.strip():
        raise ValueError("a locked rulebook needs rules")
    p = _slot_file("locked", _sl(spec_or_slot, current_input))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"rules": rules_text.strip(), "locked_at": time.strftime("%Y-%m-%d %H:%M"),
                             "by": by}, indent=1))


def unlock(spec_or_slot: str, current_input=None) -> None:
    _slot_file("locked", _sl(spec_or_slot, current_input)).unlink(missing_ok=True)


def slots() -> list[dict]:
    """Every rulebook the engine has written: which specialist and task, how many versions, locked or not."""
    d = RULES_DIR / "history"
    out = []
    for p in sorted(d.glob("*.jsonl")) if d.exists() else []:
        h = history(p.stem)
        if h:
            out.append({"slot": p.stem, "specialist": h[-1].get("specialist"), "task": h[-1].get("task"),
                        "versions": len(h), "n": h[-1]["n"], "created": h[-1]["created"],
                        "locked": locked(p.stem) is not None})
    return out


def rulebook(specialist: str, current_input) -> tuple[str, int]:
    """(rules, n): the rules implied by this workflow's n corrections for this specialist, or ('', n)."""
    if not _RULES_ON.get() or specialist in FREE_FORM_OUTPUT:
        return "", 0
    golds = [e for e, _ in _pool(specialist, current_input)]
    fixed = locked(specialist, current_input)
    if fixed:
        return fixed["rules"], len(golds)
    wrong = [e for e, _ in _pool(specialist, current_input, rejected=True)]
    if len(golds) < RULES_MIN:
        return "", len(golds)
    shown = sorted(
        f"- INPUT: {_flatten(_content(e.get('input')))[:500]}\n  CORRECT OUTPUT: "
        + json.dumps({k: v for k, v in (e.get("output") or {}).items() if k not in _NOT_A_DECISION},
                     default=str)
        for e in golds)
    counter = sorted(
        f"- INPUT: {_flatten(_content(e.get('input')))[:500]}\n  WRONG OUTPUT: "
        + json.dumps({k: v for k, v in (e.get("output") or {}).items() if k not in _NOT_A_DECISION},
                     default=str) + (f"\n  WHY IT'S WRONG: {e['reason']}" if e.get("reason") else "")
        for e in wrong)
    task = {k: v for k, v in (current_input or {}).items() if k not in CONTENT_KEYS}
    key = hashlib.sha256(json.dumps([specialist, task, shown] + ([counter] if counter else []),
                                    default=str).encode()).hexdigest()[:20]
    with _RULES_LOCK:
        key_lock = _KEY_LOCKS.setdefault(key, threading.Lock())
    with key_lock:                                   # induce once per pool, even under parallel calls
        if key not in _RULES_MEM:
            path = RULES_DIR / f"{specialist}-{key}.json"
            if path.exists():
                _RULES_MEM[key] = json.loads(path.read_text())["rules"]
            else:
                from .core import brain
                _RULES_MEM[key] = brain(
                    f"A '{specialist}' step does this task: {json.dumps(task, default=str)}\n\n"
                    f"Below are {len(golds)} inputs with the output a human reviewer marked CORRECT. The "
                    "reviewer's conventions were never written down. Work out the rules they follow — "
                    "including non-obvious conventions and which rule wins when an input matches two — and "
                    "write them as a short numbered rulebook someone new could apply, highest-precedence rules "
                    "first. Base every rule on these examples; don't invent rules they don't support. "
                    "Return only the rulebook.\n\n" + "\n".join(shown)
                    + ("\n\nThe reviewer also REJECTED these outputs; make sure the rules rule them out:\n"
                       + "\n".join(counter) if counter else "")).strip()
                RULES_DIR.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"specialist": specialist, "n": len(golds), "task": task,
                                            "rules": _RULES_MEM[key]}, indent=1, default=str))
                hist = _slot_file("history", slot(specialist, current_input))
                hist.parent.mkdir(parents=True, exist_ok=True)
                with hist.open("a") as fh:
                    fh.write(json.dumps({"created": time.strftime("%Y-%m-%d %H:%M"), "n": len(golds),
                                         "rejected": len(wrong), "key": key, "specialist": specialist,
                                         "task": task, "rules": _RULES_MEM[key]}, default=str) + "\n")
    return _RULES_MEM[key], len(golds)


def block(specialist: str, current_input, k: int = 6) -> str:
    """A prompt block of the learned rulebook and the relevant golds, or '' if there are none — or if
    the cached train-time policy says few-shot doesn't help this specialist (1C: checkers skip it,
    mappers keep it)."""
    if not policy_on(specialist):
        return ""
    book, n = rulebook(specialist, current_input)
    ex = retrieve(specialist, current_input, k)
    if not ex and not book:
        return ""
    parts = []
    if book:
        parts.append(f"RULES a human reviewer's {n} past corrections for this exact task imply — apply them; "
                     f"where a rule and your first instinct disagree, the rule wins:\n{book}")
    if not ex:
        return "\n\n".join(parts)
    parts.append("Here are examples of the CORRECT input → output for this exact task, "
                 "curated by a human reviewer:")
    for e in ex:
        parts.append(f"INPUT: {json.dumps(e['input'], default=str)}\n"
                     f"OUTPUT: {json.dumps(e['output'], default=str)}")
    parts.append("Follow the pattern these examples establish — especially where it differs "
                 "from your first instinct. They encode the reviewer's judgment; match it.")
    return "\n\n".join(parts)
