"""Build a MATCH config from the Congress bills already harvested — same policy area or not.

Kind-A / externally grounded: the pair label is real — two bills either share the same CRS policy area or
don't. Task: given two bill titles, decide same-policy-area. Reuses state/harvest/congress_candidates.json
(bills + their policyArea). A third, unrelated domain for `match`.

    python tools/harvest/congress_match.py --ingest     # scope 'legislation'
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.examples import save_example

SCOPE = "legislation"
SRC = Path("state/harvest/congress_candidates.json")
CRITERIA = "whether the two bills address the same policy area"
PER_SIDE = 16


def _pairs(by_area):
    areas = list(by_area)
    pos, neg = [], []
    for a, bills in by_area.items():                        # positives: two bills, same policy area
        for k in range(min(3, len(bills) - 1)):
            pos.append({"a": bills[k], "b": bills[k + 1], "same": True})
    for i, a in enumerate(areas):                           # negatives: two bills, different areas
        other = areas[(i + 1) % len(areas)]
        for k in range(3):
            if k < len(by_area[a]) and k < len(by_area[other]):
                neg.append({"a": by_area[a][k], "b": by_area[other][-(k + 1)], "same": False})
    return pos[:PER_SIDE] + neg[:PER_SIDE]


def ingest():
    if not SRC.exists():
        sys.exit("no candidates — run tools/harvest/congress_classify.py first.")
    by_area = {}
    for c in json.loads(SRC.read_text()):
        by_area.setdefault(c["label"], []).append(c["item"]["title"])
    cands = _pairs(by_area)
    Path(f"state/examples/{SCOPE}/match.jsonl").unlink(missing_ok=True)
    for c in cands:
        save_example("match", {"a": c["a"], "b": c["b"], "criteria": CRITERIA},
                     {"same": c["same"], "confidence": 1.0,
                      "reasoning": "Ground truth is the bills' real CRS policy areas."}, scope_name=SCOPE)
    from collections import Counter
    print(f"ingested {len(cands)} match golds -> state/examples/{SCOPE}/match.jsonl")
    print("balance:", dict(Counter(c["same"] for c in cands)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ingest", action="store_true")
    ap.parse_args()
    ingest()
