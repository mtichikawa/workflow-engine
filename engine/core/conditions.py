"""Safe evaluator for edge `when` conditions — no eval, no code execution.

Grammar:
    expr       := or
    or         := and ('or' and)*
    and        := unary ('and' unary)*
    unary      := 'not' unary | comparison
    comparison := ref (OP rhs)?          # a bare ref is a truthiness test
    OP         := == | != | >= | <= | > | < | in | not in
    rhs        := "quoted" | number | true | false | null | (bare word -> string)
    ref        := payload.field | step.field | step   (resolved by the caller)

`evaluate(expr, resolve)` — `resolve(ref)` returns the ref's value (or None if absent).
None conditions / empty string evaluate to True (an unconditional edge).
"""

from __future__ import annotations

_OPS = ["==", "!=", ">=", "<=", ">", "<"]   # longest-first so >= beats >


def evaluate(expr: str | None, resolve) -> bool:
    if not expr or not expr.strip():
        return True
    return _or(expr.strip(), resolve)


def _split_top(s: str, sep: str) -> list[str]:
    """Split on `sep` at the top level, ignoring occurrences inside quotes."""
    out, depth_q, buf, i = [], None, [], 0
    tok = f" {sep} "
    while i < len(s):
        c = s[i]
        if c in "\"'":
            depth_q = None if depth_q == c else (c if depth_q is None else depth_q)
            buf.append(c); i += 1; continue
        if depth_q is None and s[i:i + len(tok)] == tok:
            out.append("".join(buf).strip()); buf = []; i += len(tok); continue
        buf.append(c); i += 1
    out.append("".join(buf).strip())
    return out


def _or(s, resolve):
    parts = _split_top(s, "or")
    return any(_and(p, resolve) for p in parts) if len(parts) > 1 else _and(s, resolve)


def _and(s, resolve):
    parts = _split_top(s, "and")
    return all(_unary(p, resolve) for p in parts) if len(parts) > 1 else _unary(s, resolve)


def _unary(s, resolve):
    s = s.strip()
    if s.startswith("not "):
        return not _unary(s[4:], resolve)
    return _comparison(s, resolve)


def _comparison(s, resolve):
    s = s.strip()
    # ' in ' / ' not in ' membership
    for kw, negate in ((" not in ", True), (" in ", False)):
        if kw in s:
            lhs, rhs = s.split(kw, 1)
            member = resolve(lhs.strip())
            container = resolve(rhs.strip())     # both sides are refs (e.g. label in allowed)
            try:
                res = member in container
            except TypeError:
                res = False
            return (not res) if negate else res
    for op in _OPS:
        if op in s:
            lhs, rhs = s.split(op, 1)
            return _apply(op, resolve(lhs.strip()), _literal(rhs.strip(), resolve))
    # bare ref -> truthiness
    return bool(resolve(s))


def _apply(op, a, b):
    try:
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if op == ">":
            return a > b
        if op == "<":
            return a < b
        if op == ">=":
            return a >= b
        if op == "<=":
            return a <= b
    except TypeError:
        return False
    return False


def _literal(tok: str, resolve):
    t = tok.strip()
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        return t[1:-1]
    low = t.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    # a bare word compared against a ref value -> treat as a string literal
    return t
