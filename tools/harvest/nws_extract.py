"""Harvest an EXTRACT config from the National Weather Service — pull the affected areas from an alert.

Kind-A / externally grounded: the gold is the alert's structured `areaDesc` (the affected zones), which
the alert's own text names. Task: extract the affected areas from the alert prose. Fuzzy set-F1 vs the
real area list. A third, unrelated domain for `extract`. No auth (User-Agent required).

    python tools/harvest/nws_extract.py [--ingest]     # scope 'weather'
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_get
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.examples import save_example

SCOPE = "weather"
CAND = Path("state/harvest/nws_extract_candidates.json")
TARGET = "the geographic areas (counties / zones) affected by the alert"
URL = "https://api.weather.gov/alerts/active?status=actual&message_type=alert"
HEADERS = [f"User-Agent: (engine-research, {os.environ.get('NWS_CONTACT', 'set NWS_CONTACT to your email')})", "Accept: application/geo+json"]


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(curl_get(URL, headers=HEADERS, timeout=30))
    cands, seen = [], set()
    for feat in data.get("features", []):
        p = feat.get("properties", {})
        areas = [a.strip() for a in (p.get("areaDesc") or "").split(";") if a.strip()]
        headline = (p.get("headline") or "").strip()
        desc = " ".join((p.get("description") or "").split())
        text = (headline + " — " + desc)[:700]
        key = text[:80].lower()
        # keep alerts naming a handful of areas, with enough prose
        if 2 <= len(areas) <= 6 and len(text) > 80 and key not in seen:
            seen.add(key)
            cands.append({"text": text, "items": [a.lower() for a in areas]})
        if len(cands) >= 30:
            break
    CAND.write_text(json.dumps(cands, indent=2))
    print(f"wrote {len(cands)} candidates -> {CAND}")


def ingest():
    cands = json.loads(CAND.read_text())
    Path(f"state/examples/{SCOPE}/extract.jsonl").unlink(missing_ok=True)
    for c in cands:
        save_example("extract", {"text": c["text"], "target": TARGET},
                     {"items": c["items"], "reasoning": "Ground truth is the alert's structured areaDesc."},
                     scope_name=SCOPE)
    print(f"ingested {len(cands)} extract golds -> state/examples/{SCOPE}/extract.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
