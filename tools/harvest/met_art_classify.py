"""Harvest a CLASSIFY config from The Metropolitan Museum of Art's open Collection API.

Kind-A / externally grounded (see docs/standards.md): the label is the Met's OWN catalogued
curatorial `department` — a fact recorded by museum curators, not by me. Task: given an object's
title / medium / date / culture / period, predict which of 8 departments holds it. Real 8-way
classification on real labels; validates a classify config with zero input from Mike.

    python tools/harvest/met_art_classify.py            # harvest -> candidates (checkpointed)
    python tools/harvest/met_art_classify.py --ingest    # write golds to scope 'art'

No auth. Public domain / open-access metadata (https://www.metmuseum.org/about-the-met/policies-and-
documents/open-access). We keep only short factual catalog fields.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.examples import save_example

API = "https://collectionapi.metmuseum.org/public/collection/v1"
SCOPE = "art"
CAND = Path("state/harvest/met_art_candidates.json")

# 8 distinguishable-but-non-trivial departments (id -> canonical name = the ground-truth label set).
DEPARTMENTS = {
    10: "Egyptian Art",
    13: "Greek and Roman Art",
    6: "Asian Art",
    14: "Islamic Art",
    4: "Arms and Armor",
    19: "Musical Instruments",
    11: "European Paintings",
    21: "Photographs",
}
CATEGORIES = list(DEPARTMENTS.values())
CRITERIA = "which Met curatorial department holds this object"
PER_DEPT = 5              # golds per department
FIELDS = ("title", "medium", "objectDate", "culture", "period", "classification")


def _get(url: str, tries: int = 4):
    # The Met's CDN blocks urllib's TLS fingerprint (403) but allows curl — shell out, like the
    # gh-based harvester does. The CDN also throttles bursts with transient 403s, so back off + retry.
    for attempt in range(tries):
        out = subprocess.run(["curl", "-sSf", "--max-time", "25", url], capture_output=True, text=True)
        if out.returncode == 0:
            return json.loads(out.stdout or "{}")
        time.sleep(1.5 * (attempt + 1))     # linear backoff on throttle
    raise RuntimeError(f"curl failed after {tries} tries: {out.stderr.strip()[:120]}")


def _usable(obj: dict, dept_name: str) -> dict | None:
    """Keep an object only if it has enough descriptive signal and matches the expected department."""
    if obj.get("department") != dept_name:
        return None
    item = {k: (obj.get(k) or "").strip() for k in FIELDS}
    # need a title and at least one of medium/culture/period so the task isn't degenerate
    if not item["title"] or not (item["medium"] or item["culture"] or item["period"]):
        return None
    return {k: v for k, v in item.items() if v}


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if CAND.exists():                                     # resume: keep what we already pulled
        done = {c["item"]["title"]: c for c in json.loads(CAND.read_text())}
    candidates = list(done.values())
    for dept_id, dept_name in DEPARTMENTS.items():
        have = sum(1 for c in candidates if c["label"] == dept_name)
        if have >= PER_DEPT:
            print(f"  {dept_name}: already {have}")
            continue
        ids = _get(f"{API}/objects?departmentIds={dept_id}").get("objectIDs") or []
        # sample ACROSS the list (not just the oldest ids) for variety
        step = max(1, len(ids) // 400)
        pool = ids[::step]
        for oid in pool:
            if have >= PER_DEPT:
                break
            try:
                obj = _get(f"{API}/objects/{oid}")
            except Exception:  # noqa: BLE001
                continue
            item = _usable(obj, dept_name)
            if not item or item["title"] in {c["item"]["title"] for c in candidates}:
                continue
            candidates.append({"item": item, "label": dept_name, "objectID": oid})
            have += 1
            CAND.write_text(json.dumps(candidates, indent=2))   # checkpoint EVERY keep
            time.sleep(0.05)
        print(f"  {dept_name}: {have}")
    print(f"\nwrote {len(candidates)} candidates -> {CAND}")


def ingest():
    if not CAND.exists():
        sys.exit("no candidates — run without --ingest first.")
    cands = json.loads(CAND.read_text())
    Path(f"state/examples/{SCOPE}/classify.jsonl").unlink(missing_ok=True)   # fresh config
    # categories = the departments actually present in the harvest (keeps the label space honest)
    categories = sorted({c["label"] for c in cands})
    n = 0
    for c in cands:
        inp = {"item": c["item"], "categories": categories, "criteria": CRITERIA}
        out = {"label": c["label"], "confidence": 1.0,
               "reasoning": f"The Met catalogues this object under the {c['label']} department."}
        save_example("classify", inp, out, scope_name=SCOPE)
        n += 1
    print(f"ingested {n} art-classify golds -> state/examples/{SCOPE}/classify.jsonl")
    from collections import Counter
    print("per department:", dict(Counter(c["label"] for c in cands)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    args = ap.parse_args()
    ingest() if args.ingest else harvest()
