"""Build a SUMMARIZE config from the arXiv papers already harvested (no new fetch).

Kind-A / externally grounded: the real short form is the paper's TITLE (author-written), the long text
is its abstract. Task: distil the abstract into a one-line title; graded by lexical recall of the real
title's key words. Reuses state/harvest/arxiv_candidates.json — run the arXiv classify harvester first.

    python tools/harvest/arxiv_summarize.py --ingest    # write golds to scope 'science'
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.examples import save_example

SCOPE = "science"
SRC = Path("state/harvest/arxiv_candidates.json")
BRIEF = "a single-line paper title capturing the core contribution"


def ingest():
    if not SRC.exists():
        sys.exit("no arXiv candidates — run tools/harvest/arxiv_classify.py first.")
    papers = json.loads(SRC.read_text())
    Path(f"state/examples/{SCOPE}/summarize.jsonl").unlink(missing_ok=True)
    n = 0
    for p in papers:
        item = p["item"]
        if not item.get("title") or not item.get("abstract"):
            continue
        save_example("summarize",
                     {"text": item["abstract"], "brief": BRIEF},
                     {"summary": item["title"]},
                     scope_name=SCOPE)
        n += 1
    print(f"ingested {n} summarize golds (abstract->title) -> state/examples/{SCOPE}/summarize.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true", help="(only mode — reuses arxiv candidates)")
    ap.parse_args()
    ingest()
