"""Does learning from examples help, specialist by specialist? Few-shot off / examples only / examples + rulebook.

    python evals/fewshot_onoff.py            # -> evals/blind-results/fewshot-onoff.json

Every public example set (state/examples/<domain>/<specialist>.jsonl with a matcher and >= 8 examples) is
scored LEAVE-ONE-OUT in three conditions: each example is held out in turn, the specialist runs on its
input with the OTHER examples of that domain available (or none), and its output is compared with the
held-out one by the same matcher the evals use. NOT a blind set: these are the engine's own curated
examples, which it was developed alongside — read the result as "where does few-shot help, hurt or do
nothing", not as a headline accuracy. Wilson 95% intervals; one sample per condition.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.blind import pmap, rate                      # noqa: E402
from evals.examples_eval import MATCH                    # noqa: E402

EX = ROOT / "state/examples"
SKIP_SCOPES = {"t1", "t2", "baseline"}                   # test scratch; baseline holds 3-11 mixed examples
MIN = 8
CONDITIONS = ("off", "examples", "examples+rulebook")


def sets() -> list[tuple[str, str, list[dict]]]:
    out = []
    for d in sorted(EX.iterdir()):
        if not d.is_dir() or d.name in SKIP_SCOPES or d.name.startswith("wf-"):
            continue
        for f in sorted(d.glob("*.jsonl")):
            if f.stem in MATCH and not f.stem.endswith(".holdout"):
                golds = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
                golds = [g for g in golds if g.get("verdict") != "rejected"]
                if len(golds) >= MIN:
                    out.append((d.name, f.stem, golds))
    return out


def run() -> dict:
    from engine import fewshot, specialists  # noqa: F401
    from engine.core import get
    fewshot.RULES_DIR = ROOT / "state/eval-rulebooks"    # leave-one-out makes one rulebook per held-out
                                                         # example: keep them out of the real history
    jobs = [(dom, spec, i, golds, cond) for dom, spec, golds in sets()
            for i in range(len(golds)) for cond in CONDITIONS]

    def one(j):
        dom, spec, i, golds, cond = j
        held, rest = golds[i], golds[:i] + golds[i + 1:]
        with fewshot.force(cond != "off"), fewshot.rules(cond == "examples+rulebook"), fewshot.using(spec, rest):
            out = get(spec).run(held["input"], {})
        return bool(MATCH[spec](out, held.get("output", {})))

    hits = pmap(one, jobs, workers=8)
    rows: dict = {}
    for (dom, spec, _, golds, cond), h in zip(jobs, hits):
        r = rows.setdefault((dom, spec), {"domain": dom, "specialist": spec, "n": len(golds), **{c: 0 for c in CONDITIONS},
                                          "errors": 0})
        if isinstance(h, dict):                              # pmap returns {"error": ...} on a crash
            r["errors"] += 1
        else:
            r[cond] += h
    table = []
    for r in rows.values():
        for c in CONDITIONS:
            r[c] = rate(r[c], r["n"])
        table.append(r)
    tot = {c: rate(sum(r[c]["k"] for r in table), sum(r["n"] for r in table)) for c in CONDITIONS}
    return {"what": "leave-one-out over the public curated examples (not blind)", "sets": len(table),
            "examples": sum(r["n"] for r in table), "total": tot, "by_set": table,
            "measured": time.strftime("%Y-%m-%d %H:%M %Z")}


if __name__ == "__main__":
    res = run()
    out = ROOT / "evals/blind-results/fewshot-onoff.json"
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res["total"], indent=1))
