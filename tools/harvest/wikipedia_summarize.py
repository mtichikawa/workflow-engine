"""Harvest a SUMMARIZE config from Wikipedia — compress a lead paragraph to its one-line description.

Kind-A / externally grounded: the gold is the page's Wikidata short `description` (a human one-liner);
the long text is the lead-paragraph `extract`. Task: distil the lead into the one-liner. Lexical-recall
matcher (same as summarize@science). A second, unrelated domain for `summarize`. No auth.

    python tools/harvest/wikipedia_summarize.py [--ingest]     # scope 'general'
"""

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_json
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.examples import save_example

SCOPE = "general"
CAND = Path("state/harvest/wikipedia_summarize_candidates.json")
BRIEF = "a one-line description of what or who this is"
SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{t}"
TOPICS = [
    "Marie Curie", "Mount Everest", "Photosynthesis", "The Great Barrier Reef", "Ada Lovelace",
    "Black hole", "The Renaissance", "Great Wall of China", "DNA", "Leonhard Euler", "Sahara",
    "Jazz", "Volcano", "Amelia Earhart", "Antibiotic", "The Beatles", "Tokyo", "Chess",
    "Coral", "Isaac Newton", "Amazon rainforest", "Vaccine", "Serengeti", "Origami",
    "Nikola Tesla", "Great Depression", "Penicillin", "Sequoia", "Bitcoin", "Aurora",
    "Frida Kahlo", "Monsoon", "Higgs boson", "Silk Road", "Tsunami", "Espresso",
]


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    cands = []
    for t in TOPICS:
        try:
            d = curl_json(SUMMARY.format(t=urllib.parse.quote(t.replace(" ", "_"))))
        except Exception:  # noqa: BLE001
            continue
        desc = " ".join((d.get("description") or "").split())
        extract = " ".join((d.get("extract") or "").split())
        # want a substantive one-liner (not "1971 film") and a real lead paragraph
        if desc and len(desc.split()) >= 2 and len(extract) > 120 and not desc[0].isdigit():
            cands.append({"text": extract[:700], "summary": desc})
    CAND.write_text(json.dumps(cands, indent=2))
    print(f"wrote {len(cands)} candidates -> {CAND}")


def ingest():
    cands = json.loads(CAND.read_text())
    Path(f"state/examples/{SCOPE}/summarize.jsonl").unlink(missing_ok=True)
    for c in cands:
        save_example("summarize", {"text": c["text"], "brief": BRIEF},
                     {"summary": c["summary"]}, scope_name=SCOPE)
    print(f"ingested {len(cands)} summarize golds -> state/examples/{SCOPE}/summarize.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
