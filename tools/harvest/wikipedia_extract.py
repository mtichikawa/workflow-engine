"""Harvest an EXTRACT config from Wikipedia's on-this-day feed — pull the entities named in an event.

Kind-A / externally grounded: the gold is the event's linked Wikipedia pages (the notable people /
places / things it's about), which the event text names. Task: extract those entities from the prose.
Fuzzy set-F1 vs the real linked pages. A second, unrelated domain for `extract`. No auth.

    python tools/harvest/wikipedia_extract.py [--ingest]     # scope 'history'
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_json
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.examples import save_example

SCOPE = "history"
CAND = Path("state/harvest/wikipedia_extract_candidates.json")
TARGET = "the notable people, places, and things (named entities) the event is about"
FEED = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{mmdd}"
DATES = ["01/20", "03/15", "05/01", "06/28", "08/09", "09/02", "10/14", "11/22", "12/25"]


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    cands, seen = [], set()
    for mmdd in DATES:
        if len(cands) >= 30:
            break
        for e in curl_json(FEED.format(mmdd=mmdd)).get("events") or []:
            if len(cands) >= 30:
                break
            text = " ".join((e.get("text") or "").split())
            pages = [p.get("titles", {}).get("normalized") or p.get("normalizedtitle") or ""
                     for p in (e.get("pages") or [])]
            ents = [p for p in dict.fromkeys(pages) if p and "(" not in p and len(p) < 45]
            # keep events with a handful of clean entities and enough prose
            if len(text) > 40 and 2 <= len(ents) <= 6 and text not in seen:
                seen.add(text)
                cands.append({"text": text[:220], "items": [x.lower() for x in ents]})
        CAND.write_text(json.dumps(cands, indent=2))
    print(f"wrote {len(cands)} candidates -> {CAND}")


def ingest():
    cands = json.loads(CAND.read_text())
    Path(f"state/examples/{SCOPE}/extract.jsonl").unlink(missing_ok=True)
    for c in cands:
        save_example("extract", {"text": c["text"], "target": TARGET},
                     {"items": c["items"], "reasoning": "Ground truth is the event's linked Wikipedia pages."},
                     scope_name=SCOPE)
    print(f"ingested {len(cands)} extract golds -> state/examples/{SCOPE}/extract.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
