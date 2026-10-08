"""Harvest a CLASSIFY config from USDA FoodData Central — predict a food's food group.

Kind-A / externally grounded: the label is the food's catalogued `foodCategory` (USDA). Task: given a
food description, predict its food group. Real labels, zero input from Mike (needs USDA_API_KEY).

    python tools/harvest/usda_classify.py            # harvest -> candidates
    python tools/harvest/usda_classify.py --ingest    # write golds to scope 'nutrition'
"""

import argparse
import json
import os
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_json, ingest_classify, load_env

SCOPE = "nutrition"
CAND = Path("state/harvest/usda_candidates.json")
CRITERIA = "the food's food group / category"
API = "https://api.nal.usda.gov/fdc/v1/foods/search"
TERMS = ["spinach", "broccoli", "carrot", "kale", "cabbage", "apple", "banana", "orange",
         "strawberry", "grapes", "cheddar", "yogurt", "milk", "butter", "ground beef",
         "beef roast", "chicken breast", "turkey", "rice", "oats", "cornmeal", "salmon",
         "tuna", "shrimp", "bread", "muffin", "lentils", "black beans", "almonds", "peanut"]
KEEP_CATEGORIES = 6
PER_CATEGORY = 6


def harvest():
    load_env()
    key = os.environ.get("USDA_API_KEY")
    if not key:
        sys.exit("USDA_API_KEY not set in .env")
    CAND.parent.mkdir(parents=True, exist_ok=True)
    pool = []
    seen = set()
    for term in TERMS:
        q = urllib.parse.quote(term)
        url = f"{API}?query={q}&pageSize=5&dataType=Foundation,SR%20Legacy&api_key={key}"
        try:
            foods = curl_json(url).get("foods") or []
        except Exception as e:  # noqa: BLE001
            print(f"  ({term}: skipped — {e})")
            continue
        got = 0
        for f in foods:
            if got >= 2:
                break
            desc = (f.get("description") or "").strip()
            cat = (f.get("foodCategory") or "").strip()
            if desc and cat and desc.lower() not in seen:
                seen.add(desc.lower())
                pool.append({"item": {"description": desc}, "label": cat})
                got += 1
    # keep only the most-populated categories, balanced
    top = {c for c, _ in Counter(p["label"] for p in pool).most_common(KEEP_CATEGORIES)}
    kept, per = [], Counter()
    for p in pool:
        if p["label"] in top and per[p["label"]] < PER_CATEGORY:
            kept.append(p)
            per[p["label"]] += 1
    CAND.write_text(json.dumps(kept, indent=2))
    print("per category:", dict(Counter(p["label"] for p in kept)))
    print(f"wrote {len(kept)} candidates -> {CAND}")


def ingest():
    if not CAND.exists():
        sys.exit("no candidates — run without --ingest first.")
    ingest_classify(SCOPE, json.loads(CAND.read_text()), CRITERIA)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
