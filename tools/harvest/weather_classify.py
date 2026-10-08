"""Harvest a CLASSIFY config from the National Weather Service — predict an alert's event type.

Kind-A / externally grounded: the label is the alert's official NWS `event` type (Flood Warning, Heat
Advisory, ...). Task: given an alert headline + description, predict the event type. Real labels, no auth.

    python tools/harvest/weather_classify.py            # harvest -> candidates
    python tools/harvest/weather_classify.py --ingest    # write golds to scope 'weather'

Public NWS API (no auth; requires a User-Agent).
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_get, ingest_classify

SCOPE = "weather"
CAND = Path("state/harvest/weather_candidates.json")
CRITERIA = "the type of weather event the alert is about"
URL = "https://api.weather.gov/alerts/active?status=actual&message_type=alert"
HEADERS = [f"User-Agent: (engine-research, {os.environ.get('NWS_CONTACT', 'set NWS_CONTACT to your email')})", "Accept: application/geo+json"]
KEEP_EVENTS = 6
PER_EVENT = 6


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(curl_get(URL, headers=HEADERS, timeout=30))
    pool, seen = [], set()
    for feat in data.get("features", []):
        p = feat.get("properties", {})
        event = (p.get("event") or "").strip()
        headline = (p.get("headline") or "").strip()
        desc = " ".join((p.get("description") or "").split())
        # give the model the human-facing text, NOT the structured event field
        text = (headline + " — " + desc)[:600]
        key = text[:80].lower()
        if event and len(text) > 60 and key not in seen:
            seen.add(key)
            pool.append({"item": {"alert": text}, "label": event})
    top = {e for e, _ in Counter(p["label"] for p in pool).most_common(KEEP_EVENTS)}
    kept, per = [], Counter()
    for p in pool:
        if p["label"] in top and per[p["label"]] < PER_EVENT:
            kept.append(p)
            per[p["label"]] += 1
    CAND.write_text(json.dumps(kept, indent=2))
    print("per event:", dict(Counter(p["label"] for p in kept)))
    print(f"wrote {len(kept)} candidates (scanned {len(pool)}) -> {CAND}")


def ingest():
    if not CAND.exists():
        sys.exit("no candidates — run without --ingest first.")
    ingest_classify(SCOPE, json.loads(CAND.read_text()), CRITERIA)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
