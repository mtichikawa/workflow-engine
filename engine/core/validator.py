"""Validator — static analysis of a recipe graph. No execution, no brain.

Answers "is this graph well-formed and runnable?" before the dispatcher touches it, so
the dispatcher can stay dumb. Errors block a run; warnings are smells (e.g. a dangling
output — a step whose result nothing reads, like an ungated `verify`).

    findings = validate(recipe)         # list of Finding(level, msg)
    if is_valid(recipe): ...            # no errors
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import specialist as registry
from .recipe import Recipe

_KEYWORDS = {"and", "or", "not", "true", "false", "null", "none", "in"}


@dataclass
class Finding:
    level: str          # "error" | "warning"
    msg: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.msg}"


def validate(recipe: Recipe, check_contracts: bool = True) -> list[Finding]:
    out: list[Finding] = []
    ids = set(recipe.step_ids())

    # 1. edges reference real steps
    for e in recipe.edges:
        for end in (e.src, e.dst):
            if end not in ids:
                out.append(Finding("error", f"edge touches unknown step '{end}'"))

    # 2. an entry exists
    entries = recipe.entry_steps()
    if not entries:
        out.append(Finding("error", "no entry step — every step has a forward in-edge (a cycle with no start)"))

    # 3. every step is reachable from an entry
    adj: dict[str, list[str]] = {}
    for e in recipe.edges:
        adj.setdefault(e.src, []).append(e.dst)
    seen, stack = set(), list(entries)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack += adj.get(n, [])
    for sid in sorted(ids - seen):
        out.append(Finding("error", f"step '{sid}' is unreachable from any entry"))

    # 4. an exit exists (a step with no forward out-edge)
    terminals = [s.id for s in recipe.steps
                 if not [e for e in recipe.out_edges(s.id) if not recipe.is_backward(e)]]
    if not terminals:
        out.append(Finding("error", "no exit — every step has a forward out-edge (nothing terminates)"))

    # 5. backward (loop) edges must have a stopping condition
    for e in recipe.edges:
        if recipe.is_backward(e) and not (e.when and e.when.strip()):
            out.append(Finding("error",
                       f"loop edge {e.src}->{e.dst} has no `when` — it can only stop at the guard"))

    # 6. condition references must be payload or a real step
    for e in recipe.edges:
        for h in _ref_heads(e.when):
            if h != "payload" and h not in ids:
                out.append(Finding("error", f"condition on {e.src}->{e.dst} references unknown '{h}'"))

    # 7. dangling output (warning): a non-terminal step whose output nothing reads
    referenced: set[str] = set()
    for s in recipe.steps:
        for src in _sources(s.inputs):
            referenced.add(src.split(".")[0])
    for e in recipe.edges:
        referenced |= _ref_heads(e.when)
    for s in recipe.steps:
        has_forward_out = any(not recipe.is_backward(e) for e in recipe.out_edges(s.id))
        if s.id not in referenced and has_forward_out:
            out.append(Finding("warning",
                       f"step '{s.id}' output is never read by any input or condition (dangling)"))

    # 8. lone guarded gate (warning): a step whose ONLY out-edge is conditional dead-ends the work-item
    #    whenever that guard is false — the classic missing fail/else path. (A step with two branches, or
    #    a guard plus a loop-back, is fine — that's handled.)
    for s in recipe.steps:
        outs = recipe.out_edges(s.id)
        if len(outs) == 1 and outs[0].when and outs[0].when.strip():
            out.append(Finding("warning",
                       f"step '{s.id}' has a single guarded out-edge (when {outs[0].when!r}) and no other path — "
                       f"the work-item dead-ends whenever that guard is false; add an else/fail path or make it a deliberate endpoint"))

    # 9. specialists exist and their required inputs are provided
    if check_contracts:
        have = registry.all_specialists()
        for s in recipe.steps:
            if s.specialist not in have:
                out.append(Finding("error", f"step '{s.id}' uses unknown specialist '{s.specialist}'"))
                continue
            provided = set(s.config) | set(s.inputs)
            missing = [f for f in have[s.specialist].contract.input if f not in provided]
            if missing:
                out.append(Finding("error",
                           f"step '{s.id}' ({s.specialist}) is missing contract inputs {missing}"))

    return out


def is_valid(recipe: Recipe, check_contracts: bool = True) -> bool:
    return not [f for f in validate(recipe, check_contracts) if f.level == "error"]


def _ref_heads(text: str | None) -> set[str]:
    if not text:
        return set()
    text = re.sub(r"'[^']*'|\"[^\"]*\"", " ", text)          # drop quoted literals
    heads = set()
    for m in re.finditer(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", text):   # full ref token
        head = m.group(0).split(".")[0]                     # only the head, not the field
        if head.lower() in _KEYWORDS:
            continue
        heads.add(head)
    return heads


def _sources(inputs):
    for v in inputs.values():
        if isinstance(v, str):
            yield v
        elif isinstance(v, dict):
            yield from _sources(v)
        elif isinstance(v, list):
            for e in v:
                if isinstance(e, str):
                    yield e
                elif isinstance(e, dict):
                    yield from _sources(e)
