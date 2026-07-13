"""Gate-as-example-factory — your corrections at the gate become labeled examples.

Easy human loop:
  1. `engine review <run_id>`  -> writes an editable JSON of each gated item's specialist
     outputs. Edit any `output` you'd correct; leave the good ones; set `approve:false` to skip.
  2. `engine capture <run_id>` -> saves every (input, final-output) as a labeled example in
     state/examples/<specialist>.jsonl, then approves the gates.

Those examples accumulate per specialist — the fuel for few-shot improvement and future
evals (the learning loop; you're the corrector for now). Mechanical steps (fetch/act) are
skipped — there's nothing to learn there.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import scope

# The single owner of the example-store layout. Everyone (fewshot, trainer, eval, harvest)
# reads/writes examples through here — one chokepoint where scoping is enforced.
# Layout: state/examples/<scope>/<specialist>.jsonl  (scope = "baseline" or a tenant).
EX_ROOT = Path("state/examples")
REVIEW_DIR = Path("output")
SKIP = {"fetch", "act"}


def path(specialist: str, scope_name: str) -> Path:
    return EX_ROOT / scope_name / f"{specialist}.jsonl"


def save_example(specialist: str, inp, out, scope_name: str | None = None) -> None:
    """Append a gold to one scope (default: the active write scope — tenant if set, else baseline)."""
    target = scope_name or scope.write_scope()
    p = path(specialist, target)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps({"input": inp, "output": out}, default=str) + "\n")


def load_layered(specialist: str, layers: list[str] | None = None) -> list[tuple[dict, str]]:
    """Golds tagged with their source layer: [(record, scope_name), ...]. The tag is in-memory
    only (never written to the record / the prompt) — it lets retrieval report the layer split."""
    out = []
    for layer in (layers if layers is not None else scope.read_layers()):
        p = path(specialist, layer)
        if p.exists():
            out.extend((json.loads(line), layer)
                       for line in p.read_text().splitlines() if line.strip())
    return out


def load_examples(specialist: str, layers: list[str] | None = None) -> list[dict]:
    """All golds for a specialist across the active read chain (baseline first, tenant on top)."""
    return [rec for rec, _ in load_layered(specialist, layers)]


def move_examples(specialist: str, from_scope: str, to_scope: str) -> int:
    """Relabel: move a specialist's exemplars from one scope to another (append to dest, remove
    source). Corrects a mislabeled layer — e.g. a voice wrongly saved under 'baseline' belongs in a
    tailored scope (learning-loop 1B). Returns the number of records moved; a no-op if none."""
    src = path(specialist, from_scope)
    if not src.exists():
        return 0
    lines = [ln for ln in src.read_text().splitlines() if ln.strip()]
    if not lines:
        src.unlink()
        return 0
    dst = path(specialist, to_scope)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("a") as fh:
        fh.write("\n".join(lines) + "\n")
    src.unlink()
    return len(lines)


def count_examples(specialist: str, scope_name: str | None = None) -> int:
    if scope_name is not None:
        p = path(specialist, scope_name)
        return sum(1 for _ in p.open()) if p.exists() else 0
    return len(load_examples(specialist))


def build_review(board, recipe) -> dict:
    items = {}
    for item_id in sorted({c.item_id for c in board.with_status("gated")}):
        steps = {}
        for step_id, output in board.context.get(item_id, {}).items():
            spec = recipe.step(step_id).specialist
            if spec in SKIP:
                continue
            card = board.card(item_id, step_id)
            steps[step_id] = {"specialist": spec, "input": card.input, "output": output}
        items[item_id] = {"approve": True, "steps": steps}
    return {"run_id": board.run_id, "recipe": board.recipe, "items": items}


def write_review(board, recipe) -> Path:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    path = REVIEW_DIR / f"review-{board.run_id}.json"
    path.write_text(json.dumps(build_review(board, recipe), indent=2, default=str))
    return path


def load_review(run_id: str) -> dict:
    return json.loads((REVIEW_DIR / f"review-{run_id}.json").read_text())


def capture(review: dict) -> tuple[int, list[str]]:
    n, approved = 0, []
    for item_id, item in review["items"].items():
        if not item.get("approve", True):
            continue
        approved.append(item_id)
        for step in item["steps"].values():
            save_example(step["specialist"], step["input"], step["output"])
            n += 1
    return n, approved
