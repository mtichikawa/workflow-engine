"""Harvest a CLASSIFY config from TheMealDB — predict a dish's cuisine from its ingredients.

Kind-A / externally grounded: the label is the database's catalogued `strArea` (cuisine). Task:
given a dish name + its ingredient list, predict the cuisine. Real labels, zero input from Mike.

    python tools/harvest/mealdb_classify.py            # harvest -> candidates
    python tools/harvest/mealdb_classify.py --ingest    # write golds to scope 'cooking'

Public TheMealDB test API (no auth). We keep dish name + ingredients + cuisine (facts).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_json, ingest_classify

SCOPE = "cooking"
CAND = Path("state/harvest/mealdb_candidates.json")
CRITERIA = "the dish's cuisine, inferred from its ingredients"
API = "https://www.themealdb.com/api/json/v1/1"
PER_AREA = 6
AREAS = ["Italian", "Mexican", "Japanese", "Indian", "French", "Chinese", "Greek"]


def _ingredients(meal: dict) -> list[str]:
    out = []
    for i in range(1, 21):
        ing = (meal.get(f"strIngredient{i}") or "").strip()
        if ing:
            out.append(ing.lower())
    return out


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if CAND.exists():
        done = {c["item"]["name"]: c for c in json.loads(CAND.read_text())}
    candidates = list(done.values())
    for area in AREAS:
        have = sum(1 for c in candidates if c["label"] == area)
        if have >= PER_AREA:
            print(f"  {area}: already {have}")
            continue
        listing = curl_json(f"{API}/filter.php?a={area}").get("meals") or []
        for stub in listing:
            if have >= PER_AREA:
                break
            meal = (curl_json(f"{API}/lookup.php?i={stub['idMeal']}").get("meals") or [None])[0]
            if not meal:
                continue
            ings = _ingredients(meal)
            name = (meal.get("strMeal") or "").strip()
            if not name or len(ings) < 3 or name in {c["item"]["name"] for c in candidates}:
                continue
            candidates.append({"item": {"name": name, "ingredients": ings}, "label": area})
            have += 1
            CAND.write_text(json.dumps(candidates, indent=2))   # checkpoint
        print(f"  {area}: {have}")
    print(f"\nwrote {len(candidates)} candidates -> {CAND}")


def ingest():
    if not CAND.exists():
        sys.exit("no candidates — run without --ingest first.")
    ingest_classify(SCOPE, json.loads(CAND.read_text()), CRITERIA)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
