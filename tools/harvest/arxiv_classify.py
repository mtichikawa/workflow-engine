"""Harvest a CLASSIFY config from arXiv — predict a paper's primary subject category.

Kind-A / externally grounded: the label is the AUTHOR-assigned `primary_category` (arXiv requires
authors to categorize their own submissions). Task: given title + abstract, predict which of N
cross-field categories a paper belongs to. Real labels, zero input from Mike.

    python tools/harvest/arxiv_classify.py            # harvest -> candidates
    python tools/harvest/arxiv_classify.py --ingest    # write golds to scope 'science'

Public arXiv API (no auth). We keep only title + abstract + category (facts / author metadata).
"""

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_get, ingest_classify

SCOPE = "science"
CAND = Path("state/harvest/arxiv_candidates.json")
CRITERIA = "the paper's primary arXiv subject category (its field)"
PER_CAT = 6

# cross-FIELD categories (distinct disciplines, not near-neighbors) -> a real, non-trivial task.
CATEGORIES = {
    "cs.CL": "Computation and Language",
    "math.PR": "Probability",
    "q-bio.NC": "Neurons and Cognition",
    "astro-ph.GA": "Astrophysics of Galaxies",
    "econ.EM": "Econometrics",
    "eess.SP": "Signal Processing",
    "cond-mat.supr-con": "Superconductivity",
}
ATOM = "{http://www.w3.org/2005/Atom}"
ARX = "{http://arxiv.org/schemas/atom}"


def _clean(s: str) -> str:
    return " ".join((s or "").split())


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    candidates = []
    # ONE combined query across all categories -> no per-request burst for arXiv to throttle.
    q = "+OR+".join(f"cat:{c}" for c in CATEGORIES)
    url = (f"https://export.arxiv.org/api/query?search_query={q}"
           f"&sortBy=submittedDate&sortOrder=descending&max_results=300")
    feed = ET.fromstring(curl_get(url, timeout=60))
    seen = set()
    for entry in feed.findall(f"{ATOM}entry"):
        prim = entry.find(f"{ARX}primary_category")
        prim = prim.get("term") if prim is not None else None
        if prim not in CATEGORIES:                       # keep only papers PRIMARY-in our set
            continue
        if sum(1 for c in candidates if c["label"] == prim) >= PER_CAT:
            continue
        title = _clean(entry.findtext(f"{ATOM}title", ""))
        abstract = _clean(entry.findtext(f"{ATOM}summary", ""))[:700]
        if not title or len(abstract) < 120 or title in seen:
            continue
        seen.add(title)
        candidates.append({"item": {"title": title, "abstract": abstract}, "label": prim})
        CAND.write_text(json.dumps(candidates, indent=2))   # checkpoint
    from collections import Counter
    print("per category:", dict(Counter(c["label"] for c in candidates)))
    print(f"wrote {len(candidates)} candidates -> {CAND}")


def ingest():
    if not CAND.exists():
        sys.exit("no candidates — run without --ingest first.")
    ingest_classify(SCOPE, json.loads(CAND.read_text()), CRITERIA)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
