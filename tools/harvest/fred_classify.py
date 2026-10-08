"""Harvest a CLASSIFY config from FRED — predict an economic series' topic.

Kind-A / externally grounded: the label comes from the series' real FRED tag (gdp, cpi, unemployment,
...). Task: given a data series' title, predict its economic topic. Real labels, zero input from Mike
(needs FRED_API_KEY).

    python tools/harvest/fred_classify.py            # harvest -> candidates
    python tools/harvest/fred_classify.py --ingest    # write golds to scope 'economics'
"""

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_json, ingest_classify, load_env

SCOPE = "economics"
CAND = Path("state/harvest/fred_candidates.json")
CRITERIA = "the economic topic the data series measures"
API = "https://api.stlouisfed.org/fred/tags/series"
PER_TAG = 6
# FRED tag -> clean topic label (deliberately distinct economic areas)
TAGS = {
    "gdp": "GDP & Output",
    "cpi": "Prices & Inflation",
    "unemployment": "Employment",
    "interest rate": "Interest Rates",
    "housing": "Housing",
    "exports": "Trade",
}


def harvest():
    load_env()
    key = os.environ.get("FRED_API_KEY")
    if not key:
        sys.exit("FRED_API_KEY not set in .env")
    CAND.parent.mkdir(parents=True, exist_ok=True)
    candidates = []
    seen = set()
    for tag, label in TAGS.items():
        q = urllib.parse.quote(tag)
        url = (f"{API}?tag_names={q}&file_type=json&limit=40&order_by=popularity"
               f"&sort_order=desc&api_key={key}")
        have = 0
        for s in curl_json(url).get("seriess") or []:
            if have >= PER_TAG:
                break
            title = (s.get("title") or "").strip()
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            candidates.append({"item": {"title": title}, "label": label})
            have += 1
        CAND.write_text(json.dumps(candidates, indent=2))
        print(f"  {label}: {have}")
    print(f"\nwrote {len(candidates)} candidates -> {CAND}")


def ingest():
    if not CAND.exists():
        sys.exit("no candidates — run without --ingest first.")
    ingest_classify(SCOPE, json.loads(CAND.read_text()), CRITERIA)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
