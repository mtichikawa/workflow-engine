"""Blind evaluations — every number the engine claims, measured on test sets nobody tuned on.

    python evals/blind.py seal                  # hash every test set in evals/blind-sets/ BEFORE scoring
    python evals/blind.py triage                # medical-line triage on blind patient messages
    python evals/blind.py routing               # learning from corrections: a protocol it can't know
    python evals/blind.py validator             # seeded faults vs the static validator (no model)
    python evals/blind.py composer              # blind requests: runnable plans, and gaps flagged not faked

Rules (docs/blind-evals.md): each set was written by an agent that saw neither the code under test nor
any training examples, then labelled again by a second blind agent; only items both labelled the same
are scored. Sets are sealed (sha256 in evals/blind-sets/SEALED.json) before the first score and scored
once; `score` refuses a set whose hash changed. Every result carries n, a baseline and a Wilson 95% CI.
All data is SYNTHETIC. Results land in evals/blind-results/<name>.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SETS = ROOT / "evals" / "blind-sets"
OUT = ROOT / "evals" / "blind-results"
SEALED = SETS / "SEALED.json"
WORKERS = 8


# ---------------------------------------------------------------- shared
def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    """95% Wilson score interval for k successes in n trials (sound at 0 and n, unlike the normal one)."""
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rate(k: int, n: int) -> dict:
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


def load(name: str) -> list[dict]:
    path = SETS / name
    sealed = json.loads(SEALED.read_text()) if SEALED.exists() else {}
    if name not in sealed:
        raise SystemExit(f"{name} is not sealed — run `python evals/blind.py seal` before scoring")
    if hashlib.sha256(path.read_bytes()).hexdigest() != sealed[name]["sha256"]:
        raise SystemExit(f"{name} changed after it was sealed — a changed set must be a NEW set")
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def pmap(fn, items, workers: int = WORKERS):
    """Run fn over items in parallel; a failure is recorded as {"error": ...}, never dropped."""
    def safe(x):
        try:
            return fn(x)
        except Exception as e:  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}"}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(safe, items))


def save(name: str, result: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    result["measured"] = time.strftime("%Y-%m-%d %H:%M %Z")
    (OUT / f"{name}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in result.items() if k != "items"}, indent=1, ensure_ascii=False))


def seal(_args) -> None:
    sealed = json.loads(SEALED.read_text()) if SEALED.exists() else {}
    for p in sorted(SETS.glob("*.jsonl")):
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if p.name in sealed and sealed[p.name]["sha256"] != h:
            raise SystemExit(f"{p.name} was already sealed with a different hash — write a new set instead")
        sealed.setdefault(p.name, {"sha256": h, "sealed": time.strftime("%Y-%m-%d %H:%M %Z"),
                                   "lines": sum(1 for l in p.read_text().splitlines() if l.strip())})
    SEALED.write_text(json.dumps(sealed, indent=1))
    print(json.dumps(sealed, indent=1))


# ---------------------------------------------------------------- 1. the medical line
KEYWORDS = re.compile(
    r"\b(pain|hurt|hurts|bleed\w*|blood|spotting|fever|headache|swell\w*|puffy|dizzy|nause\w*|vomit\w*|"
    r"cramp\w*|contraction\w*|leak\w*|fluid|rash|itch\w*|medic\w*|pill\w*|tylenol|ibuprofen|advil|zoloft|"
    r"prescription|dose|depress\w*|anxiety|panic|suicid\w*|harm|sad|crying|sleep|infection|jaundice|"
    r"movement|moving|kick\w*|normal|safe|dolor|sangr\w*|fiebre|medicina)\b", re.I)


def triage(_args) -> None:
    from engine import specialists  # noqa: F401
    from engine.core import get
    from engine.live import care_intake as case
    items = load("triage.jsonl")
    clf = get("classify")
    cats = ["medical", "non-medical"]

    def engine_policy(it):
        return clf.run({"item": it["text"]}, {"categories": cats, "criteria": case.MEDICAL_CRITERIA})["label"]

    def bare_model(it):        # baseline: the same model, no written policy
        return clf.run({"item": it["text"]}, {"categories": cats,
                                              "criteria": "whether the message is medical"})["label"]

    def keyword(it):           # baseline: what a rules-only filter would do
        return "medical" if KEYWORDS.search(it["text"]) else "non-medical"

    result = {"set": "triage.jsonl", "n": len(items), "policy": case.MEDICAL_CRITERIA, "systems": {}, "items": []}
    preds = {"engine (policy)": pmap(engine_policy, items), "same model, no policy": pmap(bare_model, items),
             "keyword rule": [keyword(i) for i in items]}
    for name, ps in preds.items():
        result["systems"][name] = _binary(items, ps, "medical")
    for it, *ps in zip(items, *preds.values()):
        result["items"].append({**it, "pred": dict(zip(preds, ps))})
    save("triage", result)


def _binary(items, preds, pos):
    def cell(sub):
        tp = sum(1 for i, p in sub if i["label"] == pos and p == pos)
        fn = sum(1 for i, p in sub if i["label"] == pos and p != pos)
        fp = sum(1 for i, p in sub if i["label"] != pos and p == pos)
        tn = sum(1 for i, p in sub if i["label"] != pos and p != pos)
        return {"caught (sensitivity)": rate(tp, tp + fn), "false alarms": rate(fp, fp + tn),
                "missed": [i["id"] for i, p in sub if i["label"] == pos and p != pos],
                "false_alarm_ids": [i["id"] for i, p in sub if i["label"] != pos and p == pos],
                "errors": sum(1 for _, p in sub if isinstance(p, dict))}
    pairs = list(zip(items, [p if isinstance(p, str) else p for p in preds]))
    return {"all": cell(pairs), "hard only": cell([x for x in pairs if x[0].get("hard")]),
            "spanish": cell([x for x in pairs if x[0].get("lang") == "es"])}


# ---------------------------------------------------------------- 2. learning from corrections
def routing(args) -> None:
    """Learning a protocol from corrections. Set 1 (routing) was scored with examples-only learning
    before the rulebook existed; set 2 (routing2) was written afterwards and scores both methods."""
    from engine import fewshot, specialists  # noqa: F401
    from engine.core import get
    name = args.set or "routing"
    items = load(f"{name}.jsonl")
    protocol = (SETS / f"{name}_protocol.md").read_text()
    public = (SETS / f"{name}_public.txt").read_text().strip()
    queues = sorted({i["queue"] for i in items})
    rng = random.Random(20261014)
    shuffled = items[:]
    rng.shuffle(shuffled)
    test, pool = shuffled[:150], shuffled[150:]
    clf = get("classify")
    crit_public = f"which team's queue this message belongs in. The queues: {public}"
    crit_rules = f"which queue this message belongs in, following this routing protocol exactly:\n{protocol}"

    def gold(it, criteria):
        return {"input": {"item": it["text"], "categories": queues, "criteria": criteria},
                "output": {"label": it["queue"], "confidence": 1.0, "reasoning": "corrected by a reviewer"}}

    def run(criteria, examples, rulebook):
        def one(it):
            return clf.run({"item": it["text"]}, {"categories": queues, "criteria": criteria})["label"]
        with fewshot.force(bool(examples)), fewshot.using("classify", examples), fewshot.rules(rulebook):
            return pmap(one, test)

    sizes = (10, 25, 50, 100, len(pool))
    conditions = [("no corrections, queue names only", crit_public, 0, False)]
    conditions += [(f"{n} corrections, examples only", crit_public, n, False) for n in sizes]
    if name != "routing":                    # set 1 predates the rulebook; it stays scored exactly once
        conditions += [(f"{n} corrections, rulebook + examples", crit_public, n, True) for n in sizes]
    conditions += [("written protocol, no corrections (upper reference)", crit_rules, 0, False)]
    result = {"set": f"{name}.jsonl", "n_test": len(test), "n_pool": len(pool), "split_seed": 20261014,
              "learning": "examples only = the 6 most similar corrections (fewshot.retrieve); rulebook + examples "
                          "= rules the brain induces from ALL corrections (fewshot.rulebook), then the same 6",
              "conditions": {}, "items": [{"id": i["id"], "queue": i["queue"], "tricky": i.get("tricky")} for i in test]}
    for cname, crit, n, rb in conditions:
        exs = [gold(i, crit) for i in pool[:n]]
        t0 = time.time()
        preds = run(crit, exs, rb)
        ok = [p == i["queue"] for p, i in zip(preds, test)]
        tricky = [o for o, i in zip(ok, test) if i.get("tricky")]
        result["conditions"][cname] = {"corrections": n, "accuracy": rate(sum(ok), len(ok)),
                                      "tricky only": rate(sum(tricky), len(tricky)),
                                      "errors": sum(1 for p in preds if isinstance(p, dict)),
                                      "seconds": round(time.time() - t0, 1)}
        for row, p in zip(result["items"], preds):
            row[cname] = p
        print(cname, result["conditions"][cname]["accuracy"], flush=True)
    save(name, result)


# ---------------------------------------------------------------- 3. the validator
def validator(_args) -> None:
    from evals.faults import run_faults
    save("validator", run_faults())


# ---------------------------------------------------------------- 4. the composer
def composer(_args) -> None:
    from engine import specialists  # noqa: F401
    from engine.composer import compose
    items = load("composer.jsonl")

    def one(it):
        r = compose(it["request"])
        return {"runnable": r["runnable"], "gaps": [g.get("name") for g in r["gaps"]], "missing": r["missing"],
                "errors": r["errors"], "steps": [s["specialist"] for s in r["steps"]]}
    outs = pmap(one, items, workers=6)
    poss = [(i, o) for i, o in zip(items, outs) if i["label"] == "possible"]
    imp = [(i, o) for i, o in zip(items, outs) if i["label"] == "impossible"]
    flagged = lambda o: bool(o.get("gaps") or o.get("missing"))
    result = {"set": "composer.jsonl", "n": len(items), "items": [{**i, "out": o} for i, o in zip(items, outs)],
              "possible": {"n": len(poss),
                           "runnable plan, no gap claimed": rate(sum(1 for _, o in poss if o.get("runnable") and not flagged(o)), len(poss)),
                           "flagged a gap anyway (over-cautious)": rate(sum(1 for _, o in poss if flagged(o)), len(poss)),
                           "not runnable (validator errors)": rate(sum(1 for _, o in poss if o.get("errors")), len(poss))},
              "impossible": {"n": len(imp),
                             "flagged the gap (honest)": rate(sum(1 for _, o in imp if flagged(o)), len(imp)),
                             "faked it (runnable, no gap)": rate(sum(1 for _, o in imp if o.get("runnable") and not flagged(o)), len(imp))},
              "crashes": sum(1 for o in outs if "error" in o)}
    save("composer", result)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["seal", "triage", "routing", "validator", "composer"])
    ap.add_argument("--set", help="routing: which sealed set (routing | routing2)")
    a = ap.parse_args()
    {"seal": seal, "triage": triage, "routing": routing, "validator": validator, "composer": composer}[a.what](a)


if __name__ == "__main__":
    main()
