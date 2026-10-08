"""Harvest a CLASSIFY config from StackExchange — which community a question belongs to.

Kind-A / externally grounded: the label is the StackExchange SITE the question was actually asked on
(cooking, law, movies, ...). Task: given a question title, predict its community. One config that
literally spans unrelated fields — a clean demonstration of niche-agnostic classification. Real labels,
zero input from Mike.

    python tools/harvest/stackexchange_classify.py            # harvest -> candidates
    python tools/harvest/stackexchange_classify.py --ingest    # write golds to scope 'communities'

Public StackExchange API (no auth, rate-limited). We keep the question title + site (facts).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_json, ingest_classify

SCOPE = "communities"
CAND = Path("state/harvest/stackexchange_candidates.json")
CRITERIA = "which StackExchange community (topic area) the question was asked on"
API = "https://api.stackexchange.com/2.3/questions"
PER_SITE = 7

# site key -> canonical community label (the ground truth). Deliberately unrelated fields.
SITES = {
    "cooking": "Cooking",
    "law": "Law",
    "movies": "Movies & TV",
    "history": "History",
    "gardening": "Gardening",
    "travel": "Travel",
    "scifi": "Science Fiction & Fantasy",
}


def _clean(s: str) -> str:
    return " ".join((s or "").split())


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if CAND.exists():
        done = {c["item"]["title"]: c for c in json.loads(CAND.read_text())}
    candidates = list(done.values())
    for site, label in SITES.items():
        have = sum(1 for c in candidates if c["label"] == label)
        if have >= PER_SITE:
            continue
        url = f"{API}?order=desc&sort=votes&site={site}&pagesize=20&filter=default"
        for q in curl_json(url).get("items") or []:
            if have >= PER_SITE:
                break
            title = _clean(q.get("title", ""))
            if not title or title in {c["item"]["title"] for c in candidates}:
                continue
            candidates.append({"item": {"title": title}, "label": label})
            have += 1
            CAND.write_text(json.dumps(candidates, indent=2))   # checkpoint
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
