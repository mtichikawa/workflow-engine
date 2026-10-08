"""Harvest a CLASSIFY config from the Federal Register — predict a document's issuing agency.

Kind-A / externally grounded: the label is the agency that officially issued the document (recorded
by the Office of the Federal Register). Task: given a document's title + abstract, predict which
federal agency issued it. Real government metadata, zero input from Mike.

    python tools/harvest/fedreg_classify.py            # harvest -> candidates
    python tools/harvest/fedreg_classify.py --ingest    # write golds to scope 'government'

Public Federal Register API (no auth). We keep title + abstract + agency (public-record facts).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_json, ingest_classify

SCOPE = "government"
CAND = Path("state/harvest/fedreg_candidates.json")
CRITERIA = "which federal agency issued the document"
API = "https://www.federalregister.gov/api/v1/documents.json"
PER_AGENCY = 6

# slug -> canonical agency name (the ground-truth label). Distinct subject-matter agencies.
AGENCIES = {
    "environmental-protection-agency": "Environmental Protection Agency",
    "internal-revenue-service": "Internal Revenue Service",
    "food-and-drug-administration": "Food and Drug Administration",
    "federal-communications-commission": "Federal Communications Commission",
    "securities-and-exchange-commission": "Securities and Exchange Commission",
    "federal-aviation-administration": "Federal Aviation Administration",
}


def _clean(s: str) -> str:
    return " ".join((s or "").split())


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if CAND.exists():
        done = {c["item"]["title"]: c for c in json.loads(CAND.read_text())}
    candidates = list(done.values())
    for slug, name in AGENCIES.items():
        have = sum(1 for c in candidates if c["label"] == name)
        if have >= PER_AGENCY:
            print(f"  {name}: already {have}")
            continue
        url = (f"{API}?conditions[agencies][]={slug}&per_page=20&order=newest"
               f"&fields[]=title&fields[]=abstract&fields[]=agencies")
        for doc in curl_json(url).get("results") or []:
            if have >= PER_AGENCY:
                break
            title = _clean(doc.get("title", ""))
            abstract = _clean(doc.get("abstract") or "")
            names = {a.get("name") for a in doc.get("agencies") or []}
            # clean label: exactly one of OUR target agencies issued it (avoid ambiguous co-issued docs)
            if len(names & set(AGENCIES.values())) != 1:
                continue
            if not title or len(abstract) < 80 or title in {c["item"]["title"] for c in candidates}:
                continue
            candidates.append({"item": {"title": title, "abstract": abstract[:700]}, "label": name})
            have += 1
            CAND.write_text(json.dumps(candidates, indent=2))   # checkpoint
        print(f"  {name}: {have}")
    print(f"\nwrote {len(candidates)} candidates -> {CAND}")


def ingest():
    if not CAND.exists():
        sys.exit("no candidates — run without --ingest first.")
    ingest_classify(SCOPE, json.loads(CAND.read_text()), CRITERIA)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
