"""Harvest a SEQUENCE config from Wikipedia's on-this-day feed — order historical events by date.

Kind-A / externally grounded: the label is the real chronological order, from each event's actual
`year`. Each puzzle is a set of ~6 events presented in a neutral (non-chronological) order; the task is
to order them earliest-first. The event TEXT omits the year, so it's genuine historical-reasoning, not
date-reading. Scored by Kendall tau vs the true year order. Zero input from Mike.

    python tools/harvest/wikipedia_sequence.py            # harvest -> candidates
    python tools/harvest/wikipedia_sequence.py --ingest    # write golds to scope 'history'

Public Wikipedia REST API (no auth).
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
CAND = Path("state/harvest/wikipedia_sequence_candidates.json")
CRITERIA = "chronological order, earliest event first"
FEED = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{mmdd}"
DATES = ["01/15", "03/10", "04/25", "06/18", "07/04", "09/12", "10/29", "12/07"]
PER_PUZZLE = 6
PUZZLES_PER_DATE = 3


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    puzzles = []
    for mmdd in DATES:
        try:
            events = curl_json(FEED.format(mmdd=mmdd)).get("events") or []
        except Exception as e:  # noqa: BLE001
            print(f"  {mmdd}: skipped — {e}")
            continue
        # clean, de-duped, sorted oldest->newest; spread across the whole range via striding
        seen, clean = set(), []
        for e in events:
            txt = " ".join((e.get("text") or "").split())
            yr = e.get("year")
            if txt and isinstance(yr, int) and txt not in seen:
                seen.add(txt)
                clean.append({"year": yr, "text": txt[:220]})
        clean.sort(key=lambda x: x["year"])
        if len(clean) < PER_PUZZLE * PUZZLES_PER_DATE:
            stride = 1
        else:
            stride = len(clean) // (PER_PUZZLE * PUZZLES_PER_DATE)
        spread = clean[::stride]
        for p in range(PUZZLES_PER_DATE):
            group = spread[p * PER_PUZZLE:(p + 1) * PER_PUZZLE]
            if len(group) < PER_PUZZLE:
                break
            # present in a neutral order (alphabetical by text — uncorrelated with year); gold = by year
            present = sorted(group, key=lambda x: x["text"])
            items = [{"id": f"e{i+1}", "text": g["text"], "_year": g["year"]}
                     for i, g in enumerate(present)]
            gold_order = [it["id"] for it in sorted(items, key=lambda x: x["_year"])]
            puzzles.append({
                "items": [{"id": it["id"], "text": it["text"]} for it in items],
                "order": gold_order,
                "years": {it["id"]: it["_year"] for it in items},
            })
        CAND.write_text(json.dumps(puzzles, indent=2))
        print(f"  {mmdd}: {sum(1 for _ in range(PUZZLES_PER_DATE))} puzzle(s) attempted")
    print(f"\nwrote {len(puzzles)} puzzles -> {CAND}")


def ingest():
    if not CAND.exists():
        sys.exit("no candidates — run without --ingest first.")
    puzzles = json.loads(CAND.read_text())
    Path(f"state/examples/{SCOPE}/sequence.jsonl").unlink(missing_ok=True)
    for p in puzzles:
        save_example("sequence",
                     {"items": p["items"], "criteria": CRITERIA},
                     {"order": p["order"],
                      "reasoning": "Ground-truth order is the events' actual years."},
                     scope_name=SCOPE)
    print(f"ingested {len(puzzles)} sequence golds -> state/examples/{SCOPE}/sequence.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
