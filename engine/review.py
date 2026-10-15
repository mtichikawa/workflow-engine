"""Review — what a person decides at the gate, and what the engine learns from it.

Every decision teaches something:
  - an output marked right, or approved untouched  → a confirmed example of what's right
  - an output the reviewer edited                  → a correction (the edit is the example)
  - an output marked wrong, with a reason          → a counterexample ("wrong, because…")
and the item as a whole is approved (the gated step's output — edited if they edited it — flows on to
the next step) or rejected (nothing downstream runs).

A fixed share of reviewed items (default 1 in 5, chosen by item id) goes to a HOLD-OUT set instead of
the learning set, so `holdout_score()` measures the specialist on cases it has never learned from.
Each decision is logged to state/review_log.jsonl, which `error_rates()` reads: how often a person had
to change or reject each step's output. Mechanical steps (fetch, act) have nothing to learn.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from . import examples
from .core import get

LOG = Path("state/review_log.jsonl")
HOLDOUT_RATE = 0.2
VERDICTS = ("right", "edited", "wrong")


def held_out(item_id: str, rate: float = HOLDOUT_RATE) -> bool:
    """Is this item kept for measuring rather than learning? Fixed by its id, so it never flips."""
    return int(hashlib.sha256(item_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < rate


def pending(board, recipe) -> list[dict]:
    """What a reviewer sees for each item waiting at a gate: every step that has produced output so far.
    Mechanical steps (fetch, act) are shown — a reviewer must see what they approve — but teach nothing
    (`learn: False`). A for-each step also carries `elements`: what each result was made from."""
    out = []
    for card in board.with_status("gated"):
        steps = []
        for step in recipe.steps:
            c = board.card(card.item_id, step.id)
            if not c or (c.output is None and c is not card):     # a held action has no output yet
                continue
            row = {"step": step.id, "specialist": step.specialist, "config": step.config, "input": c.input,
                   "output": c.output,
                   "gate": step.id == card.step_id, "learn": _learnable(step)}
            if step.each:
                row["elements"] = [_element_label(i) for i in (c.input or {}).get("each", [])]
            steps.append(row)
        out.append({"item": card.item_id, "gate": card.step_id,
                    "payload": board.items[card.item_id]["payload"], "steps": steps})
    return out


def _learnable(step) -> bool:
    """Judgment steps teach; mechanical ones (fetch, and anything that acts outside the engine) don't."""
    return step.specialist not in examples.SKIP and not getattr(get(step.specialist), "side_effect", False)


def _element_label(inp: dict) -> str:
    """The part of a for-each element's input a person recognises: its content field, else all of it."""
    from .fewshot import CONTENT_KEYS
    for k in CONTENT_KEYS:
        if isinstance(inp.get(k), str):
            return inp[k]
    return json.dumps(inp, default=str)[:300]


def decide(disp, recipe, item_id: str, approve: bool, verdicts: dict | None = None,
           reason: str = "", by: str = "", holdout_rate: float = HOLDOUT_RATE) -> dict:
    """Apply one reviewer's decision on one gated item.

    `verdicts` maps step id → {"verdict": "right"|"edited"|"wrong", "output": <edited output>,
    "reason": <why it's wrong>}. Steps not mentioned count as "right" when the item is approved and
    teach nothing when it's rejected (a rejection says something is wrong, not what). Returns a
    summary of what was learned."""
    board = disp.board
    gate = next((c.step_id for c in board.cards_for(item_id) if c.status == "gated"), None)
    if gate is None:
        raise ValueError(f"{item_id} is not waiting at a gate")
    verdicts = verdicts or {}
    for sid, v in verdicts.items():
        if v.get("verdict") not in VERDICTS:
            raise ValueError(f"{sid}: verdict must be one of {VERDICTS}")
        if v["verdict"] == "edited" and not isinstance(v.get("output"), dict):
            raise ValueError(f"{sid}: an edit needs the edited output")
    to_holdout = held_out(item_id, holdout_rate)
    learned = Counter()
    for step in recipe.steps:
        card = board.card(item_id, step.id)
        if not card or card.output is None or not _learnable(step):
            continue
        v = verdicts.get(step.id, {"verdict": "right"} if approve else None)
        if v is None:
            continue
        out = v["output"] if v["verdict"] == "edited" else card.output
        pairs = _pairs(step, card.input, out)
        if v["verdict"] == "edited":
            contract = get(step.specialist).contract.output
            for _, o in pairs:
                missing = [f for f in contract if f not in o]
                if missing:
                    raise ValueError(f"{step.id}: the edited output is missing {missing}")
        for inp, o in pairs:
            if v["verdict"] == "wrong":
                examples.save_example(step.specialist, inp, o, verdict="rejected",
                                      reason=v.get("reason", "") or reason)
            else:
                examples.save_example(step.specialist, inp, o, holdout=to_holdout)
        learned[v["verdict"]] += 1
        _log({"ts": int(time.time()), "run": board.run_id, "recipe": recipe.name, "item": item_id,
              "step": step.id, "specialist": step.specialist, "verdict": v["verdict"],
              "holdout": to_holdout and v["verdict"] != "wrong", "by": by})
    gate_edit = verdicts.get(gate, {})
    if approve:
        disp.approve(item_id, gate, output=gate_edit.get("output") if gate_edit.get("verdict") == "edited" else None)
    else:
        disp.reject(item_id, gate, reason)
    disp.run()
    board.save()
    return {"item": item_id, "approved": approve, "learned": dict(learned), "holdout": to_holdout}


def _pairs(step, inp, out) -> list[tuple]:
    """(input, output) examples one step teaches. A for-each step teaches one per element."""
    if not step.each:
        return [(inp, out)]
    ins, outs = inp.get("each", []), (out or {}).get("results")
    if not isinstance(outs, list) or len(outs) != len(ins):
        raise ValueError(f"{step.id}: a for-each output needs one result per element ({len(ins)})")
    return list(zip(ins, outs))


def _log(rec: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def error_rates(recipe: str | None = None) -> list[dict]:
    """Per workflow step: how many reviewed outputs a person kept, edited or marked wrong."""
    if not LOG.exists():
        return []
    rows = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]
    by = {}
    for r in rows:
        if recipe and r["recipe"] != recipe:
            continue
        by.setdefault((r["recipe"], r["step"], r["specialist"]), Counter())[r["verdict"]] += 1
    out = []
    for (rec, step, spec), c in sorted(by.items()):
        n = sum(c.values())
        out.append({"recipe": rec, "step": step, "specialist": spec, "reviewed": n, "right": c["right"],
                    "edited": c["edited"], "wrong": c["wrong"],
                    "error_rate": round((c["edited"] + c["wrong"]) / n, 3) if n else None})
    return out


def holdout_score(specialist: str, config: dict | None = None) -> dict | None:
    """Run the specialist, as it is now (learning from its examples), on its hold-out cases and score
    it with the same matcher the evals use. None if there's no hold-out set or no matcher."""
    from evals.examples_eval import MATCH
    held = examples.load_holdout(specialist)
    match = MATCH.get(specialist)
    if not held or not match:
        return None
    spec = get(specialist)
    hits = sum(bool(match(spec.run(h["input"], config or {}), h.get("output", {}))) for h in held)
    return {"specialist": specialist, "holdout": len(held), "right": hits, "rate": round(hits / len(held), 3)}
