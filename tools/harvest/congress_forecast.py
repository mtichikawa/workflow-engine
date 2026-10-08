"""Harvest a FORECAST config from Congress.gov — predict whether a bill became law, from its title.

Kind-A / externally grounded: the outcome is the bill's real fate in the completed 117th Congress.
Positives = bills that became public law (`/v3/law/117`); negatives = a sample of bills that did not
(most bills). Situation = the bill title only. Balanced. A third, unrelated domain for `forecast` — and
an honest hard case (most signal about passage isn't in the title). Needs CONGRESS_API_KEY.

    python tools/harvest/congress_forecast.py [--ingest]     # scope 'legislation'
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_json, load_env
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.examples import save_example

SCOPE = "legislation"
CAND = Path("state/harvest/congress_forecast_candidates.json")
OUTCOMES = ["became law", "did not become law"]
CRITERIA = "whether the bill ultimately became law"
PER_SIDE = 16


def harvest():
    load_env()
    key = os.environ.get("CONGRESS_API_KEY")
    if not key:
        sys.exit("CONGRESS_API_KEY not set in .env")
    CAND.parent.mkdir(parents=True, exist_ok=True)
    pos, seen = [], set()
    laws = curl_json(f"https://api.congress.gov/v3/law/117?limit={PER_SIDE*2}&format=json&api_key={key}")
    for b in laws.get("bills") or []:
        title = (b.get("title") or "").strip()
        if title and title.lower() not in seen and len(pos) < PER_SIDE:
            seen.add(title.lower()); pos.append({"situation": {"title": title}, "outcome": OUTCOMES[0]})
    neg = []
    lst = curl_json(f"https://api.congress.gov/v3/bill/117/hr?limit=250&format=json&api_key={key}")
    for b in lst.get("bills") or []:
        title = (b.get("title") or "").strip()
        # heuristic negative: a bill still at an early/committee stage did not become law
        action = ((b.get("latestAction") or {}).get("text") or "").lower()
        became = "became public law" in action or "signed by president" in action
        if title and not became and title.lower() not in seen and len(neg) < PER_SIDE:
            seen.add(title.lower()); neg.append({"situation": {"title": title}, "outcome": OUTCOMES[1]})
    cands = pos + neg
    CAND.write_text(json.dumps(cands, indent=2))
    from collections import Counter
    print("balance:", dict(Counter(c["outcome"] for c in cands)))
    print(f"wrote {len(cands)} candidates -> {CAND}")


def ingest():
    cands = json.loads(CAND.read_text())
    Path(f"state/examples/{SCOPE}/forecast.jsonl").unlink(missing_ok=True)
    for c in cands:
        save_example("forecast", {"situation": c["situation"], "outcomes": OUTCOMES},
                     {"prediction": c["outcome"], "confidence": 1.0,
                      "reasoning": "Ground truth is the bill's real fate in the 117th Congress."}, scope_name=SCOPE)
    print(f"ingested {len(cands)} forecast golds -> state/examples/{SCOPE}/forecast.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
