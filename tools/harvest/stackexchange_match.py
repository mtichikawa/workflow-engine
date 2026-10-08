"""Build a MATCH config from the StackExchange questions already harvested (no new fetch).

Kind-A / externally grounded: the pair label is real — two questions either came from the SAME
StackExchange community or not. Task: given two question titles, decide whether they belong to the same
topic community. Positives = same site; negatives = different sites (adjacent sites like cooking/gardening
make it non-trivial). Reuses state/harvest/stackexchange_candidates.json.

    python tools/harvest/stackexchange_match.py --ingest    # write golds to scope 'communities'
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.examples import save_example

SCOPE = "communities"
SRC = Path("state/harvest/stackexchange_candidates.json")
CRITERIA = ("whether both questions are about the SAME SUBJECT AREA (would be asked on the same "
            "topic-specific Q&A site, e.g. both cooking, both law) -- NOT whether they are the same question")
PER_SITE_POS = 2      # positive (same-site) pairs per site
PER_SITE_NEG = 2      # negative (different-site) pairs per site


def _pairs(by_site: dict) -> list[dict]:
    sites = list(by_site)
    pairs = []
    # positives: consecutive questions within a site
    for s, qs in by_site.items():
        for k in range(min(PER_SITE_POS, len(qs) - 1)):
            pairs.append({"a": qs[k], "b": qs[k + 1], "same": True})
    # negatives: question k of a site vs question k of the NEXT site (topically adjacent-ish)
    for i, s in enumerate(sites):
        other = sites[(i + 1) % len(sites)]
        qs, oqs = by_site[s], by_site[other]
        for k in range(min(PER_SITE_NEG, len(qs), len(oqs))):
            pairs.append({"a": qs[k], "b": oqs[-(k + 1)], "same": False})
    return pairs


def ingest():
    if not SRC.exists():
        sys.exit("no candidates — run tools/harvest/stackexchange_classify.py first.")
    cands = json.loads(SRC.read_text())
    by_site: dict[str, list] = {}
    for c in cands:
        by_site.setdefault(c["label"], []).append(c["item"]["title"])
    pairs = _pairs(by_site)
    Path(f"state/examples/{SCOPE}/match.jsonl").unlink(missing_ok=True)
    for p in pairs:
        save_example("match",
                     {"a": p["a"], "b": p["b"], "criteria": CRITERIA},
                     {"same": p["same"], "confidence": 1.0,
                      "reasoning": "Ground truth: the two questions' actual source communities."},
                     scope_name=SCOPE)
    from collections import Counter
    print(f"ingested {len(pairs)} match golds -> state/examples/{SCOPE}/match.jsonl")
    print("label balance:", dict(Counter(p["same"] for p in pairs)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    ap.parse_args()
    ingest()
