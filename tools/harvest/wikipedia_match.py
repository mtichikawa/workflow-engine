"""Harvest a MATCH config from Wikipedia — decide whether two names are the same real-world entity.

Kind-A / externally grounded: the pair label is real — an alias and the canonical title are the SAME
entity (a real Wikipedia redirect); two different canonical titles are NOT. Positives are filtered to
GENUINE aliases (low word-overlap with the canonical, e.g. "Samuel Clemens" ↔ "Mark Twain"), so the task
needs world knowledge, not string-matching. A third, unrelated (crisp) domain for `match`. No auth.

    python tools/harvest/wikipedia_match.py [--ingest]     # scope 'general'
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
CAND = Path("state/harvest/wikipedia_match_candidates.json")
CRITERIA = "whether the two names refer to the same real-world entity (person, place, or thing)"
API = "https://en.wikipedia.org/w/api.php?action=query&format=json&prop=redirects&rdlimit=30&rdnamespace=0&titles={t}"
ENTITIES = [
    "Mark Twain", "Lady Gaga", "Bob Dylan", "Freddie Mercury", "Malcolm X", "Elton John",
    "Vin Diesel", "Whoopi Goldberg", "Muhammad Ali", "Cat Stevens", "Snoop Dogg", "Marilyn Monroe",
    "Voltaire", "Mother Teresa", "Jay-Z", "Michael Caine", "George Orwell", "Ringo Starr",
    "Gordon Ramsay", "Pope Francis", "Vladimir Lenin", "Charles de Gaulle", "Meat Loaf", "Sting (musician)",
]
PER_SIDE = 16


def _words(s):
    return {w for w in s.lower().replace("(", " ").replace(")", " ").split() if len(w) > 2}


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    aliases = {}
    for e in ENTITIES:
        try:
            pg = list(curl_json(API.format(t=urllib.parse.quote(e)))["query"]["pages"].values())[0]
        except Exception:  # noqa: BLE001
            continue
        canon = pg["title"]
        cw = _words(canon)
        genuine = [r["title"] for r in pg.get("redirects", [])
                   if not (_words(r["title"]) & cw) and r["title"].lower() != canon.lower()
                   and len(r["title"]) > 3]
        if genuine:
            aliases[canon] = genuine[0]     # one genuine alias per entity
    canons = list(aliases)
    pos = [{"a": c, "b": aliases[c], "same": True} for c in canons]
    neg = [{"a": canons[i], "b": canons[(i + 1) % len(canons)], "same": False} for i in range(len(canons))]
    cands = pos[:PER_SIDE] + neg[:PER_SIDE]
    CAND.write_text(json.dumps(cands, indent=2))
    from collections import Counter
    print("balance:", dict(Counter(c["same"] for c in cands)))
    print("sample positives:", [(p["a"], p["b"]) for p in pos[:3]])
    print(f"wrote {len(cands)} candidates -> {CAND}")


def ingest():
    cands = json.loads(CAND.read_text())
    Path(f"state/examples/{SCOPE}/match.jsonl").unlink(missing_ok=True)
    for c in cands:
        save_example("match", {"a": c["a"], "b": c["b"], "criteria": CRITERIA},
                     {"same": c["same"], "confidence": 1.0,
                      "reasoning": "Ground truth is Wikipedia redirects (aliases of the same entity)."}, scope_name=SCOPE)
    print(f"ingested {len(cands)} match golds -> state/examples/{SCOPE}/match.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
