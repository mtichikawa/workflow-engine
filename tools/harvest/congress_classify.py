"""Harvest a CLASSIFY config from Congress.gov — predict a bill's policy area.

Kind-A / externally grounded: the label is the bill's official CRS `policyArea` (assigned by the
Congressional Research Service). Task: given a bill's title, predict its policy area. Real labels, zero
input from Mike (needs CONGRESS_API_KEY). Two-step: list bills, then fetch each detail for its policyArea.

    python tools/harvest/congress_classify.py            # harvest -> candidates
    python tools/harvest/congress_classify.py --ingest    # write golds to scope 'legislation'
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_json, ingest_classify, load_env

SCOPE = "legislation"
CAND = Path("state/harvest/congress_candidates.json")
CRITERIA = "the bill's policy area (its subject domain)"
BASE = "https://api.congress.gov/v3/bill/118"
KEEP_AREAS = 6
PER_AREA = 6
SCAN = 140                       # how many bills to fetch details for while bucketing


def harvest():
    load_env()
    key = os.environ.get("CONGRESS_API_KEY")
    if not key:
        sys.exit("CONGRESS_API_KEY not set in .env")
    CAND.parent.mkdir(parents=True, exist_ok=True)
    pool, seen = [], set()
    for billtype in ("hr", "s"):
        lst = curl_json(f"{BASE}/{billtype}?limit={SCAN // 2}&format=json&api_key={key}")
        for b in lst.get("bills") or []:
            if len(pool) >= SCAN:
                break
            num = b.get("number")
            try:
                det = curl_json(f"{BASE}/{billtype}/{num}?format=json&api_key={key}").get("bill", {})
            except Exception:  # noqa: BLE001
                continue
            title = (det.get("title") or "").strip()
            area = ((det.get("policyArea") or {}).get("name") or "").strip()
            if title and area and title.lower() not in seen:
                seen.add(title.lower())
                pool.append({"item": {"title": title}, "label": area})
                Path(CAND).write_text(json.dumps(pool, indent=2))     # checkpoint
    # keep the most-populated policy areas, balanced
    top = {a for a, _ in Counter(p["label"] for p in pool).most_common(KEEP_AREAS)}
    kept, per = [], Counter()
    for p in pool:
        if p["label"] in top and per[p["label"]] < PER_AREA:
            kept.append(p)
            per[p["label"]] += 1
    CAND.write_text(json.dumps(kept, indent=2))
    print("per area:", dict(Counter(p["label"] for p in kept)))
    print(f"wrote {len(kept)} candidates (scanned {len(pool)}) -> {CAND}")


def ingest():
    if not CAND.exists():
        sys.exit("no candidates — run without --ingest first.")
    ingest_classify(SCOPE, json.loads(CAND.read_text()), CRITERIA)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
