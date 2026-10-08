"""Clean leave-one-out score for ONE scope's golds — the campaign's per-domain eval.

`engine eval` LOOs a specialist across its whole read chain (baseline + tenant). For the
library-expansion campaign we want each domain config scored in ISOLATION (art classify without
the dev-triage baseline golds muddying the number). This loads exactly one scope's golds (public
`state/examples/<scope>/` plus `private/examples/<scope>/` when present) and runs the same leave-one-out loop as
evals/examples_eval, injecting the OTHER same-file golds as few-shot (never the held-out one).

    python tools/eval_scope.py <specialist> <scope>        # e.g. classify art
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine.specialists  # noqa: F401  -- registers the library
from engine import examples, fewshot
from engine.core import get
from evals.examples_eval import MATCH, MIN_GOLDS


def loo_scope(specialist: str, scope: str):
    golds = examples.load_examples(specialist, [scope])
    match = MATCH.get(specialist)
    if not match:
        sys.exit(f"no matcher for '{specialist}' (have: {', '.join(sorted(MATCH))})")
    if len(golds) < MIN_GOLDS:
        sys.exit(f"only {len(golds)} golds; need >= {MIN_GOLDS}")
    passed, misses = 0, []
    for i, held in enumerate(golds):
        subset = golds[:i] + golds[i + 1:]
        with fewshot.using(specialist, subset):
            out = get(specialist).run(held["input"], {})
        ok = bool(match(out, held.get("output", {})))
        passed += ok
        if not ok:
            g = held.get("output", {})
            misses.append((out, g))
    return passed, len(golds), misses


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: python tools/eval_scope.py <specialist> <scope>")
    specialist, scope = sys.argv[1], sys.argv[2]
    if not examples.count_examples(specialist, scope):
        sys.exit(f"no golds for {specialist} @ {scope}")
    passed, total, misses = loo_scope(specialist, scope)
    print(f"\n  {specialist} @ {scope}   leave-one-out   {passed}/{total}  {passed/total:.0%}")
    for out, g in misses[:8]:
        key = "label" if specialist == "classify" else next(iter(g), "?")
        print(f"    miss: predicted {out.get(key)!r}  actual {g.get(key)!r}")


if __name__ == "__main__":
    main()
