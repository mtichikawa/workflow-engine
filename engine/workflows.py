"""Saved workflows — compose once, then keep, edit and rerun without touching code.

A saved workflow is a recipe plus the request it was made from and how it takes its input, kept as
numbered versions in state/workflows/<name>/: an edit never overwrites, it adds the next version, so
any earlier one can be read, diffed or run again. Nothing is saved that fails validation.

    save("expense-lines", recipe, request="...", source={"kind": "csv"})   # -> 1
    recipe, meta = load("expense-lines")                                    # latest version
    run_id = run("expense-lines", inputs.csv_rows("march.csv"))
"""

from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path

from .core import Board, Dispatcher, Edge, Recipe, Step, Tracer, validate

DIR = Path("state/workflows")
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def to_dict(recipe: Recipe) -> dict:
    steps = []
    for s in recipe.steps:
        d = {"id": s.id, "specialist": s.specialist}
        for k, default in (("config", {}), ("inputs", {}), ("gate", False), ("join", "and"), ("each", None)):
            if getattr(s, k) != default:
                d[k] = getattr(s, k)
        steps.append(d)
    return {"steps": steps, "edges": [{"from": e.src, "to": e.dst, **({"when": e.when} if e.when else {})}
                                      for e in recipe.edges], "max_visits": recipe.max_visits}


def from_dict(name: str, d: dict) -> Recipe:
    steps = [Step(id=s["id"], specialist=s["specialist"], config=s.get("config", {}), inputs=s.get("inputs", {}),
                  gate=s.get("gate", False), join=s.get("join", "and"), each=s.get("each"))
             for s in d["steps"]]
    r = Recipe(name, steps, [Edge(e["from"], e["to"], e.get("when")) for e in d.get("edges", [])],
               d.get("max_visits", 6))
    if not d.get("edges"):
        r.edges = [Edge(a.id, b.id) for a, b in zip(steps, steps[1:])] if len(steps) > 1 else []
    return r


def _dir(name: str) -> Path:
    if not _NAME.match(name):
        raise ValueError(f"workflow name '{name}': use lowercase letters, digits and hyphens")
    return DIR / name


def versions(name: str) -> list[int]:
    d = _dir(name)
    return sorted(int(p.stem[1:]) for p in d.glob("v*.json")) if d.exists() else []


def save(name: str, recipe: Recipe | dict, request: str = "", source: dict | None = None,
         note: str = "", by: str = "") -> int:
    """Validate and store as the next version. Returns the version number; raises on any error."""
    body = recipe if isinstance(recipe, dict) else to_dict(recipe)
    rec = from_dict(name, body)
    errors = [f.msg for f in validate(rec) if f.level == "error"]
    if errors:
        raise ValueError("not saved — the workflow doesn't validate:\n  " + "\n  ".join(errors))
    prev = versions(name)
    if prev:                                     # keep the request and input settings unless changed
        _, last = load(name)
        request = request or last["request"]
        source = source or last["source"]
        if last["recipe"] == to_dict(rec) and last["source"] == source and last["request"] == request:
            return prev[-1]                      # nothing changed: no new version
    v = (prev[-1] if prev else 0) + 1
    d = _dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"v{v}.json").write_text(json.dumps({
        "name": name, "version": v, "saved": time.strftime("%Y-%m-%d %H:%M"), "by": by, "note": note,
        "request": request, "source": source or {"kind": "text"}, "recipe": to_dict(rec)}, indent=1))
    return v


def load(name: str, version: int | None = None) -> tuple[Recipe, dict]:
    vs = versions(name)
    if not vs:
        raise KeyError(f"no saved workflow '{name}'")
    v = version or vs[-1]
    meta = json.loads((_dir(name) / f"v{v}.json").read_text())
    return from_dict(name, meta["recipe"]), meta


def all_workflows() -> list[dict]:
    out = []
    for d in sorted(DIR.glob("*")) if DIR.exists() else []:
        vs = versions(d.name)
        if vs:
            _, meta = load(d.name)
            out.append({"name": d.name, "versions": len(vs), "request": meta["request"],
                        "saved": meta["saved"], "source": meta["source"], "steps": len(meta["recipe"]["steps"]),
                        "runs": len(runs(d.name))})
    return out


def diff(name: str, a: int, b: int) -> str:
    da, db = (json.dumps(load(name, v)[1]["recipe"], indent=1).splitlines() for v in (a, b))
    return "\n".join(difflib.unified_diff(da, db, f"v{a}", f"v{b}", lineterm=""))


def lookup(name: str) -> Recipe:
    """A built-in recipe or a saved workflow, by name — what approve / review / board need."""
    from .recipes import RECIPES
    if name in RECIPES:
        return RECIPES[name]
    return load(name)[0]


def run(name: str, items: list[tuple[str, dict]], version: int | None = None, auto: bool = False,
        concurrency: int = 4, run_id: str | None = None) -> str:
    """Run a saved workflow on (item_id, payload) pairs. Returns the run id; the board is in state/."""
    recipe, meta = load(name, version)
    run_id = run_id or f"{name}-{int(time.time() * 1000)}"
    board = Board(recipe=name, run_id=run_id)
    for item_id, payload in items:
        board.add_item(item_id, payload)
    Dispatcher(recipe, board, Tracer(run_id, echo=False), concurrency=concurrency).run(auto_approve=auto)
    with (_dir(name) / "runs.jsonl").open("a") as fh:
        fh.write(json.dumps({"run": run_id, "version": meta["version"], "items": len(items),
                             "at": time.strftime("%Y-%m-%d %H:%M"), "snapshot": board.snapshot()}) + "\n")
    return run_id


def runs(name: str) -> list[dict]:
    p = _dir(name) / "runs.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
