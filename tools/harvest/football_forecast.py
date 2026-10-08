"""Harvest a FORECAST config from football-data.co.uk — predict a match result before it's known.

Kind-A / externally grounded: the label is the real full-time result (FTR: H/D/A), recorded after the
match. The situation given to the specialist is only pre-match info (the two teams, league, date) --
never the score. This validates `forecast` the honest way: reality is the grader, leave-one-out over
matches whose outcome is known. Football outcomes are high-variance (home-win base rate ~48%), so this
is a genuinely hard test -- the point is a real, uninflated forecast signal, not a big number.

    python tools/harvest/football_forecast.py            # harvest -> candidates
    python tools/harvest/football_forecast.py --ingest    # write golds to scope 'sports'

Public CSV (no auth). We keep team names + league + date + result (sports facts).
"""

import argparse
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_get
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.examples import save_example

SCOPE = "sports"
CAND = Path("state/harvest/football_candidates.json")
OUTCOMES = ["home win", "draw", "away win"]
FTR = {"H": "home win", "D": "draw", "A": "away win"}
CRITERIA_LEAGUE = "English Premier League"
SEASON = "2022-23"
CSV_URL = "https://www.football-data.co.uk/mmz4281/2223/E0.csv"
N = 40                                        # sample size (LOO cost = N brain calls)


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    rows = [r for r in csv.DictReader(io.StringIO(curl_get(CSV_URL, timeout=30)))
            if r.get("FTR") in FTR and r.get("HomeTeam") and r.get("AwayTeam")]
    step = max(1, len(rows) // N)
    picked = rows[::step][:N]
    candidates = []
    for r in picked:
        candidates.append({
            "situation": {"home_team": r["HomeTeam"], "away_team": r["AwayTeam"],
                          "league": CRITERIA_LEAGUE, "season": SEASON, "date": r.get("Date", "")},
            "outcome": FTR[r["FTR"]],
            "score": f'{r["HomeTeam"]} {r.get("FTHG","")}-{r.get("FTAG","")} {r["AwayTeam"]}',
        })
    CAND.write_text(json.dumps(candidates, indent=2))
    from collections import Counter
    print("outcome dist:", dict(Counter(c["outcome"] for c in candidates)))
    print(f"wrote {len(candidates)} candidates -> {CAND}")


def ingest():
    if not CAND.exists():
        sys.exit("no candidates — run without --ingest first.")
    cands = json.loads(CAND.read_text())
    Path(f"state/examples/{SCOPE}/forecast.jsonl").unlink(missing_ok=True)
    for c in cands:
        save_example(
            "forecast",
            {"situation": c["situation"], "outcomes": OUTCOMES},
            {"prediction": c["outcome"], "confidence": 1.0,
             "reasoning": f"Actual full-time result: {c['score']}."},
            scope_name=SCOPE,
        )
    from collections import Counter
    print(f"ingested {len(cands)} forecast golds -> state/examples/{SCOPE}/forecast.jsonl")
    print("outcome dist:", dict(Counter(c["outcome"] for c in cands)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
