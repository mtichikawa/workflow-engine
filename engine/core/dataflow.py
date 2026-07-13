"""Derive a recipe's DATA-FLOW graph from its structure.

A recipe already encodes how information moves: every step's `inputs` names the exact upstream
outputs it reads (e.g. verify reads `classify.label`, `route.component`, `respond.reply`; the four
readers all read `payload`). Those references ARE the data edges — the fan-out (many readers of the
issue) and fan-in (verify/act gathering several outputs). This extracts that graph so a viewer (the
use-case explorer) can be *generated* from the real recipe, for any topology, instead of hand-drawn.

    graph = dataflow(TRIAGE)   # -> {"nodes": [...], "data_edges": [...], "control_edges": [...]}

- nodes:         IN + each step + OUT, tagged shared/domain/gate.
- data_edges:    src -> dst with the field read (from step inputs). `payload` reads become IN -> step.
- control_edges: recipe.edges (execution order + guarded gates/loops), carrying the `when` condition.
"""

from __future__ import annotations

from .recipe import Recipe


def _refs(v):
    """Every string reference inside an inputs value (str | list | dict), recursively."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [r for x in v.values() for r in _refs(x)]
    if isinstance(v, (list, tuple)):
        return [r for x in v for r in _refs(x)]
    return []


def dataflow(recipe: Recipe) -> dict:
    step_ids = {s.id for s in recipe.steps}
    nodes = [{"id": "IN", "kind": "in"}]
    for s in recipe.steps:
        kind = "gate" if s.gate else "domain" if s.domain else "shared"
        nodes.append({"id": s.id, "kind": kind, "specialist": s.specialist})
    nodes.append({"id": "OUT", "kind": "out"})

    data_edges, seen = [], set()
    for s in recipe.steps:
        for ref in _refs(s.inputs):
            head, _, field = ref.partition(".")
            src = "IN" if head == "payload" else (head if head in step_ids else None)
            if src is None:
                continue
            reads = (field or "issue") if src == "IN" else (field or "output")
            key = (src, s.id, reads)
            if key in seen:
                continue
            seen.add(key)
            data_edges.append({"src": src, "dst": s.id, "reads": reads})

    control_edges = [{"src": e.src, "dst": e.dst, "when": e.when} for e in recipe.edges]

    # OUT is fed by the terminal step(s) — those with no forward control edge out.
    has_out = {e.src for e in recipe.edges}
    for s in recipe.steps:
        if s.id not in has_out:
            data_edges.append({"src": s.id, "dst": "OUT", "reads": "result"})

    return {"nodes": nodes, "data_edges": data_edges, "control_edges": control_edges}
