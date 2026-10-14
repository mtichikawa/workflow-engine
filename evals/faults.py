"""Seeded faults vs the static validator — no model calls.

The fault KINDS come from evals/blind-sets/fault_kinds.md, written by an agent that never saw the
validator (25 statically-detectable kinds + 16 it judged undetectable). Each applicable kind is a
mutation operator here, applied at EVERY site it fits in every real recipe (triage, content, review,
refine, care_intake). A mutant counts as caught when validate() reports a finding the unmutated recipe
didn't have: an error for a kind that should BLOCK, an error or warning for one that should WARN.
Kinds that don't apply to this engine's model are listed with the reason, not silently dropped.
Control: every unmutated recipe must produce zero errors (false alarms).
"""

from __future__ import annotations

import copy
from collections import defaultdict

from engine import specialists  # noqa: F401
from engine.core import Edge, Step, get, validate
from engine.core.recipe import Recipe

NOT_APPLICABLE = {
    "entry_ambiguity": "several entry steps are a feature here (parallel starts), and zero entries can't be "
                       "expressed: a backward edge is a loop by definition, so the first step is always an entry",
    "unbounded_loop": "every recipe carries a loop guard (max_visits, default 6) — a loop can't be uncapped",
    "wire_maybe_not_run": "not attempted: needs path-sensitive analysis of OR-joins",
    "unknown_target_input": "by design: contracts list REQUIRED fields and allow extras (e.g. loop feedback)",
    "payload_field_undeclared": "the engine has no payload schema to check against",
    "overlapping_conditions": "no recipe has numeric/range splits to overlap (0 sites)",
}


def _recipes() -> list[Recipe]:
    from engine.live import care_intake
    from engine.recipes import RECIPES
    care_intake.load()
    return list(RECIPES.values()) + [care_intake.RECIPE]


def _leaves(inputs, path=()):
    for k, v in inputs.items():
        if isinstance(v, dict):
            yield from _leaves(v, path + (k,))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                if isinstance(x, str):
                    yield path + (k, i), x
        elif isinstance(v, str):
            yield path + (k,), v


def _set(inputs, path, value):
    cur = inputs
    for p in path[:-1]:
        cur = cur[p]
    cur[path[-1]] = value


def _step_refs(r: Recipe):
    """(step index, leaf path, head, field) for every input wired from another step."""
    ids = set(r.step_ids())
    for i, s in enumerate(r.steps):
        for path, ref in _leaves(s.inputs):
            head, _, field = ref.partition(".")
            if head in ids:
                yield i, path, head, field


def _ancestors(r: Recipe, sid: str) -> set:
    seen, stack = set(), [sid]
    while stack:
        for e in r.forward_in(stack.pop()):
            if e.src not in seen:
                seen.add(e.src)
                stack.append(e.src)
    return seen


def _clone(r: Recipe) -> Recipe:
    return copy.deepcopy(r)


def _rebuild(r: Recipe, steps=None, edges=None) -> Recipe:
    return Recipe(r.name, steps if steps is not None else r.steps, edges if edges is not None else r.edges,
                  r.max_visits)


def mutants(r: Recipe):
    """Yield (kind, should, description, mutated recipe) for every site each kind fits."""
    ids = r.step_ids()
    guarded = [e for e in r.edges if e.when]
    backward = [e for e in r.edges if r.is_backward(e)]

    for i, s in enumerate(r.steps):                                     # 1 duplicate id
        m = _clone(r)
        m.steps.append(copy.deepcopy(m.steps[i]))
        yield "duplicate_step_id", "block", f"second step '{s.id}'", m
    for j, e in enumerate(r.edges):                                     # 2 dangling edge
        for end in ("src", "dst"):
            m = _clone(r)
            setattr(m.edges[j], end, "ghost_step")
            yield "dangling_edge", "block", f"{e.src}->{e.dst}: {end} -> ghost_step", m
    for i, s in enumerate(r.steps):                                     # 3 unknown specialist
        m = _clone(r)
        m.steps[i].specialist = "nonexistent_specialist"
        yield "unknown_specialist", "block", s.id, m
    readers = {h for _, _, h, _ in _step_refs(r)}                       # steps whose output another step reads
    reads = {r.steps[i].id for i, _, _, _ in _step_refs(r)}             # steps that read another step
    # In this engine a step with no way in is an entry (a parallel start) and one with no way out is an exit,
    # so cutting edges is only a fault when it breaks a data dependency — those are the sites used here.
    for s in r.steps:                                                   # 5 unreachable (cut every way in)
        if r.forward_in(s.id) and s.id in reads:
            m = _clone(r)
            m.edges = [e for e in m.edges if e.dst != s.id]
            yield "unreachable_step", "block", f"no edge into '{s.id}'", m
    for s in r.steps:                                                   # 6 dead end (cut every way out)
        outs = [e for e in r.out_edges(s.id) if not r.is_backward(e)]
        if outs and s.id in readers:
            m = _clone(r)
            m.edges = [e for e in m.edges if not (e.src == s.id and not r.is_backward(e))]
            yield "no_path_to_terminal", "block", f"no edge out of '{s.id}'", m
    for e in backward:                                                  # 7 loop that can never exit
        m = _clone(r)
        next(x for x in m.edges if x.src == e.src and x.dst == e.dst and x.when == e.when).when = None
        yield "unconditional_loop", "block", f"{e.src}->{e.dst} lost its condition", m
    for s in r.steps:
        m = _clone(r)
        m.edges.append(Edge(s.id, s.id))
        yield "unconditional_loop", "block", f"self-edge on '{s.id}'", m
    for i, path, head, field in _step_refs(r):                          # 9 malformed reference
        for bad in (f"{head}..{field or 'x'}", f"{head}.", f".{field or 'x'}"):
            m = _clone(r)
            _set(m.steps[i].inputs, path, bad)
            yield "malformed_reference", "block", f"{r.steps[i].id} reads '{bad}'", m
    for i, path, head, field in _step_refs(r):                          # 10 unknown source step
        m = _clone(r)
        _set(m.steps[i].inputs, path, f"{head}x" + (f".{field}" if field else ""))
        yield "wire_unknown_source", "block", f"{r.steps[i].id} reads '{head}x'", m
    for i, path, head, field in _step_refs(r):                          # 11 unknown output field
        if field:
            m = _clone(r)
            _set(m.steps[i].inputs, path, f"{head}.no_such_field")
            yield "wire_unknown_field", "block", f"{r.steps[i].id} reads {head}.no_such_field", m
    for i, s in enumerate(r.steps):                                     # 12 reads a step that hasn't run
        refs = [(p, h, f) for (k, p, h, f) in _step_refs(r) if k == i]
        later = [x for x in ids if x != s.id and x not in _ancestors(r, s.id) and s.id in _ancestors(r, x)]
        if refs and later:
            p, _, _ = refs[0]
            out = next(iter(get(r.step(later[-1]).specialist).contract.output))
            m = _clone(r)
            _set(m.steps[i].inputs, p, f"{later[-1]}.{out}")
            yield "wire_not_upstream", "block", f"{s.id} reads downstream {later[-1]}.{out}", m
    for i, s in enumerate(r.steps):                                     # 14 required input missing
        spec = get(s.specialist)
        for f in spec.contract.input:
            m = _clone(r)
            m.steps[i].inputs.pop(f, None)
            m.steps[i].config.pop(f, None)
            yield "missing_required_input", "block", f"{s.id} lost '{f}'", m
    for i, s in enumerate(r.steps):                                     # 17 type mismatch
        spec = get(s.specialist)
        for f, typ in spec.contract.input.items():
            if typ is object:
                continue
            for a in _ancestors(r, s.id):
                hit = next(((of, ot) for of, ot in get(r.step(a).specialist).contract.output.items()
                            if ot is not object and not (isinstance(ot, type) and isinstance(typ, type)
                                                          and issubclass(ot, typ))), None)
                if hit:
                    m = _clone(r)
                    m.steps[i].config.pop(f, None)
                    m.steps[i].inputs[f] = f"{a}.{hit[0]}"
                    yield "type_mismatch", "block", f"{s.id}.{f} ({typ.__name__}) <- {a}.{hit[0]} ({hit[1].__name__})", m
                    break
    for j, e in enumerate(r.edges):                                     # 18-21 conditions
        if not e.when or "==" not in e.when:
            continue
        lhs, rhs = (x.strip() for x in e.when.split("==", 1))
        head, _, field = lhs.partition(".")
        variants = [("condition_syntax_error", "block", e.when.replace("==", "=", 1)),
                    ("condition_syntax_error", "block", e.when.replace("==", "=>", 1)),
                    ("condition_unknown_ref", "block", f"{head}.{field}z == {rhs}"),
                    ("condition_unknown_ref", "block", f"{head}z.{field} == {rhs}"),
                    ("condition_unsatisfiable", "block", f"{lhs} == {rhs[:-1]}d{rhs[-1]}" if rhs[-1:] in "'\"" else f"{lhs} == {rhs}d")]
        later = [x for x in ids if e.src in _ancestors(r, x) and x != e.dst and e.dst not in _ancestors(r, x)]
        if later:
            out = next(iter(get(r.step(later[-1]).specialist).contract.output))
            variants.append(("condition_not_upstream", "block", f"{later[-1]}.{out} == {rhs}"))
        for kind, should, w in variants:
            m = _clone(r)
            m.edges[j].when = w
            yield kind, should, f"{e.src}->{e.dst} when {w}", m
    by_src = defaultdict(list)                                          # 22 drop one side of a branch
    for e in guarded:
        if not r.is_backward(e):
            by_src[e.src].append(e)
    for src, es in by_src.items():
        others = [e for e in r.out_edges(src) if not e.when and not r.is_backward(e)]
        if len(es) >= 2 and not others:
            for e in es:
                m = _clone(r)
                m.edges = [x for x in m.edges if not (x.src == e.src and x.dst == e.dst and x.when == e.when)]
                yield "non_exhaustive_branch", "warn", f"dropped {e.src}->{e.dst} when {e.when}", m
    for e in guarded:                                                   # 24 join that can never complete
        if r.is_backward(e) or "==" not in e.when:
            continue
        lhs, rhs = (x.strip() for x in e.when.split("==", 1))
        m = _clone(r)
        dst = m.step(e.dst)
        detour = Step(f"{e.dst}_alt", dst.specialist, copy.deepcopy(dst.config), copy.deepcopy(dst.inputs))
        m.steps.insert(m.step_ids().index(e.dst), detour)
        m.edges += [Edge(e.src, detour.id, f"{lhs} != {rhs}"), Edge(detour.id, e.dst)]
        yield "join_deadlock", "block", f"{e.dst} AND-joins {e.src} (when {rhs}) with a step that runs only when not", m
    for i, s in enumerate(r.steps):                                     # 25 a side effect with no gate before it
        if s.specialist == "act":
            m = _clone(r)
            for x in m.steps:
                x.gate = False
            yield "gate_bypass", "block", f"'{s.id}' (act) with every gate removed", m


def run_faults() -> dict:
    recipes = _recipes()
    control = {r.name: [str(f) for f in validate(r) if f.level == "error"] for r in recipes}
    by_kind = defaultdict(lambda: {"sites": 0, "caught": 0, "missed": []})
    for r in recipes:
        base = {str(f) for f in validate(r)}
        for kind, should, desc, m in mutants(r):
            try:
                found = [f for f in validate(m) if str(f) not in base]
                caught = any(f.level == "error" for f in found) if should == "block" else bool(found)
            except Exception as ex:  # noqa: BLE001 — a crash is not a catch
                caught, desc = False, f"{desc} [validator crashed: {type(ex).__name__}]"
            k = by_kind[kind]
            k["should"] = should
            k["sites"] += 1
            k["caught"] += caught
            if not caught:
                k["missed"].append(f"{r.name}: {desc}")
    from evals.blind import rate
    total_sites = sum(k["sites"] for k in by_kind.values())
    total_caught = sum(k["caught"] for k in by_kind.values())
    kinds_full = sum(1 for k in by_kind.values() if k["caught"] == k["sites"])
    return {"recipes": [r.name for r in recipes],
            "false alarms on the unmutated recipes": {n: e for n, e in control.items()},
            "mutants caught": rate(total_caught, total_sites),
            "fault kinds fully caught": f"{kinds_full} of {len(by_kind)} applicable "
                                        f"({len(NOT_APPLICABLE)} of the blind list's 25 don't apply)",
            "by kind": {k: {"should": v["should"], "caught": rate(v["caught"], v["sites"]),
                            "missed (first 5)": v["missed"][:5]} for k, v in sorted(by_kind.items())},
            "not applicable": NOT_APPLICABLE}
