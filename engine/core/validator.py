"""Validator — static analysis of a recipe graph. No execution, no brain.

Answers "is this graph well-formed and runnable?" before the dispatcher touches it, so
the dispatcher can stay dumb. Errors block a run; warnings are smells (e.g. a dangling
output — a step whose result nothing reads, like an ungated `verify`).

    findings = validate(recipe)         # list of Finding(level, msg)
    if is_valid(recipe): ...            # no errors

Checks 1-9 are structural (shape, loops, references, contracts). Checks 10-17 follow the DATA:
every wire and every condition must name a step that exists and has already run, a field that
step actually produces, a compatible type and a value it can produce; AND-joins must be
satisfiable; a step with side effects must sit at or behind a full human gate; and a review policy
(sample / confidence) must read a field that exists. (Coverage measured
against an independently written list of fault kinds: evals/faults.py.)
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from . import specialist as registry
from .conditions import _literal
from .recipe import Recipe

_KEYWORDS = {"and", "or", "not", "true", "false", "null", "none", "in"}
_REF = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")
_COMPARE = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(==|!=)\s*(.+?)\s*$")


@dataclass
class Finding:
    level: str          # "error" | "warning"
    msg: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.msg}"


def validate(recipe: Recipe, check_contracts: bool = True) -> list[Finding]:
    out: list[Finding] = []

    # 0. step ids are unique (wiring and edges name steps by id)
    seen_ids: set[str] = set()
    for s in recipe.steps:
        if s.id in seen_ids:
            out.append(Finding("error", f"two steps share the id '{s.id}'"))
        seen_ids.add(s.id)
    ids = set(recipe.step_ids())

    # 1. edges reference real steps — later checks only see the edges that do
    good_edges = []
    for e in recipe.edges:
        bad = [end for end in (e.src, e.dst) if end not in ids]
        for end in bad:
            out.append(Finding("error", f"edge touches unknown step '{end}'"))
        if not bad:
            good_edges.append(e)
    if len(good_edges) != len(recipe.edges):
        recipe = Recipe(recipe.name, recipe.steps, good_edges or [], recipe.max_visits)
        recipe.edges = good_edges              # keep "no edges" as no edges, not an implied chain

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
    have = registry.all_specialists()
    if check_contracts:
        for s in recipe.steps:
            if s.specialist not in have:
                out.append(Finding("error", f"step '{s.id}' uses unknown specialist '{s.specialist}'"))
                continue
            provided = set(s.config) | set(s.inputs)
            missing = [f for f in have[s.specialist].contract.input if f not in provided]
            if missing:
                out.append(Finding("error",
                           f"step '{s.id}' ({s.specialist}) is missing contract inputs {missing}"))

    out += _dataflow(recipe, have, ids)
    return out


def _dataflow(recipe: Recipe, have: dict, ids: set) -> list[Finding]:
    """Checks 10-16: follow every wire and condition to the step it names."""
    out: list[Finding] = []
    step = {s.id: s for s in recipe.steps}
    spec = {s.id: have.get(s.specialist) for s in recipe.steps}
    anc = {s.id: _ancestors(recipe, s.id) for s in recipe.steps}
    loops = [(e.src, set(recipe.loop_body(e.dst, e.src))) for e in recipe.edges if recipe.is_backward(e)]

    def ran_before(src: str, consumer: str) -> bool:
        return src in anc[consumer] or any(src == ls and consumer in body for ls, body in loops)

    def produces(src: str, field: str):
        sp = spec.get(src)
        return None if sp is None else field in sp.contract.output

    # 10-13. wires: well-formed, an existing step (not a typo of one), already run, a real field, a fitting type
    for s in recipe.steps:
        target = spec[s.id]
        for path, ref in _leaves(s.inputs):
            head, _, tail = ref.partition(".")
            if head not in ids and head != "payload":
                near = difflib.get_close_matches(head, sorted(ids) + ["payload"], n=1, cutoff=0.8)
                if near and _REF.match(ref):
                    out.append(Finding("error", f"step '{s.id}' reads '{ref}' — no step '{head}' "
                                                f"(did you mean '{near[0]}'?)"))
                continue                                    # anything else is a literal value
            if "." in ref and not _REF.match(ref):
                out.append(Finding("error", f"step '{s.id}' reads malformed reference '{ref}'"))
                continue
            if head == "payload":
                continue
            if not ran_before(head, s.id):
                out.append(Finding("error", f"step '{s.id}' reads '{ref}', but '{head}' hasn't run by then "
                                            f"(it isn't upstream of '{s.id}')"))
            field = tail.split(".")[0] if tail else None
            if field and produces(head, field) is False:
                out.append(Finding("error", f"step '{s.id}' reads '{ref}', but '{step[head].specialist}' "
                                            f"doesn't produce '{field}'"))
            if field and len(path) == 1 and target and spec.get(head):
                want = target.contract.input.get(path[0])
                got = spec[head].contract.output.get(field)
                if _incompatible(got, want):
                    out.append(Finding("error", f"step '{s.id}' wires {ref} ({_tname(got)}) into "
                                                f"'{path[0]}', which takes {_tname(want)}"))

    # 14. conditions: valid syntax, a real field of a step that has run, a value that step can produce
    for e in recipe.edges:
        if not e.when:
            continue
        bare = re.sub(r"'[^']*'|\"[^\"]*\"", "''", e.when)
        if re.search(r"(?<![=!<>])=(?!=)|=>|=<|<>|===", bare):
            out.append(Finding("error", f"condition on {e.src}->{e.dst} has an invalid operator: {e.when!r}"))
            continue
        for part in re.split(r"\s+(?:and|or)\s+", e.when):
            part = re.sub(r"^\s*not\s+", "", part)
            m = _COMPARE.match(part)
            ref = m.group(1) if m else part.strip()
            head, _, tail = ref.partition(".")
            if head not in ids:
                continue                                    # payload, or already reported by check 6
            if head != e.src and head not in anc.get(e.src, set()):
                out.append(Finding("error", f"condition on {e.src}->{e.dst} reads '{head}', which hasn't "
                                            f"run when that edge is decided"))
            field = tail.split(".")[0] if tail else None
            if field and produces(head, field) is False:
                out.append(Finding("error", f"condition on {e.src}->{e.dst} reads '{ref}', but "
                                            f"'{step[head].specialist}' doesn't produce '{field}'"))
            if m and field and spec.get(head):
                allowed = spec[head].output_values(field, step[head].config)
                lit = _literal(m.group(3), lambda r: None)
                if allowed is not None and m.group(2) == "==" and lit not in allowed:
                    out.append(Finding("error", f"condition on {e.src}->{e.dst} compares {ref} to {lit!r}, "
                                                f"which it never produces (it produces {allowed})"))

    # 15. AND-joins that can never complete: two in-edges guarded on the same field with exclusive values
    for s in recipe.steps:
        if s.join != "and":
            continue
        guards = []
        for e in recipe.forward_in(s.id):
            g = _guard(e.when)
            if g is None:                                   # the source itself may run only under a guard
                src_in = recipe.forward_in(e.src)
                g = _guard(src_in[0].when) if len(src_in) == 1 else None
            if g:
                guards.append((e.src, g))
        for i, (a, ga) in enumerate(guards):
            for b, gb in guards[i + 1:]:
                if a != b and _exclusive(ga, gb):
                    out.append(Finding("error", f"step '{s.id}' waits for both '{a}' and '{b}', but they "
                                                f"run under exclusive conditions — it can never start"))

    # 16. a side effect needs a human gate at or before it — a full one: a review policy (sample or
    # confidence) lets some items through unseen, so it doesn't count as approval for an outside action
    for s in recipe.steps:
        sp = spec[s.id]
        if sp is not None and sp.side_effect and s.gate is not True and not any(
                step[a].gate is True for a in anc[s.id]):
            partial = isinstance(s.gate, dict) or any(isinstance(step[a].gate, dict) for a in anc[s.id])
            out.append(Finding("error", f"step '{s.id}' ({s.specialist}) acts outside the engine with no human "
                                        f"gate at or before it" + (" (a sampled or confidence gate lets items "
                                        "through unreviewed, so it doesn't count)" if partial else "")))

    # 17. a review policy must be one the dispatcher understands, reading a field that exists by then
    for s in recipe.steps:
        g = s.gate
        if g is True or g is False:
            continue
        if not isinstance(g, dict) or not g or set(g) - {"sample", "below", "confidence"}:
            out.append(Finding("error", f"step '{s.id}': gate must be true, false, or a policy with "
                                        f"'sample' and/or 'below' + 'confidence' (got {g!r})"))
            continue
        if "sample" in g and not (isinstance(g["sample"], (int, float)) and 0 < g["sample"] <= 1):
            out.append(Finding("error", f"step '{s.id}': gate sample must be a share between 0 and 1"))
        if "below" in g:
            ref = g.get("confidence")
            head, _, field = (ref or "").partition(".")
            if not isinstance(g["below"], (int, float)) or not ref:
                out.append(Finding("error", f"step '{s.id}': a 'below' gate needs a number and a "
                                            f"'confidence' reference like '{s.id}.confidence'"))
            elif head != s.id and head not in anc[s.id]:
                out.append(Finding("error", f"step '{s.id}': gate confidence '{ref}' must come from this "
                                            f"step or one before it"))
            elif spec.get(head) is not None and field.split(".")[0] not in spec[head].contract.output:
                out.append(Finding("error", f"step '{s.id}': gate confidence '{ref}' — "
                                            f"'{step[head].specialist}' doesn't produce '{field}'"))
    return out


def _ancestors(recipe: Recipe, sid: str) -> set:
    seen, stack = set(), [sid]
    while stack:
        for e in recipe.forward_in(stack.pop()):
            if e.src not in seen:
                seen.add(e.src)
                stack.append(e.src)
    return seen


def _guard(when: str | None):
    m = _COMPARE.match(when or "")
    return (m.group(1), m.group(2), _literal(m.group(3), lambda r: None)) if m else None


def _exclusive(a, b) -> bool:
    (ra, oa, va), (rb, ob, vb) = a, b
    if ra != rb:
        return False
    return (oa, ob) in (("==", "!="), ("!=", "==")) and va == vb or (oa == ob == "==" and va != vb)


def _incompatible(got, want) -> bool:
    if got in (None, object) or want in (None, object):
        return False
    gots = got if isinstance(got, tuple) else (got,)
    wants = want if isinstance(want, tuple) else (want,)
    return not any(issubclass(g, w) for g in gots for w in wants)


def _tname(t) -> str:
    return getattr(t, "__name__", str(t))


def _leaves(inputs, path=()):
    for k, v in inputs.items():
        if isinstance(v, dict):
            yield from _leaves(v, path + (k,))
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str):
                    yield path + (k,), x
        elif isinstance(v, str):
            yield path + (k,), v


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
