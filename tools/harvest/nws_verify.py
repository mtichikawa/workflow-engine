"""Harvest a VERIFY config from the National Weather Service — is this alert a serious threat?

Kind-A / externally grounded: the standard is "this alert warns of a severe or extreme threat", and the
pass/fail gold is the alert's real NWS `severity` (Severe/Extreme = pass; Minor/Moderate = fail).
Subject = the alert's headline + description. Balanced. A third, unrelated domain for `verify`. No auth.

    python tools/harvest/nws_verify.py [--ingest]     # scope 'weather'
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import curl_get
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.examples import save_example

SCOPE = "weather"
CAND = Path("state/harvest/nws_verify_candidates.json")
STANDARD = "this alert warns of a severe or extreme threat (a serious danger to life or property)"
URL = "https://api.weather.gov/alerts/active?status=actual&message_type=alert"
HEADERS = [f"User-Agent: (engine-research, {os.environ.get('NWS_CONTACT', 'set NWS_CONTACT to your email')})", "Accept: application/geo+json"]
PER_SIDE = 16


def harvest():
    CAND.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(curl_get(URL, headers=HEADERS, timeout=30))
    pos, neg, seen = [], [], set()
    for feat in data.get("features", []):
        p = feat.get("properties", {})
        sev = (p.get("severity") or "").strip()
        headline = (p.get("headline") or "").strip()
        desc = " ".join((p.get("description") or "").split())
        text = (headline + " — " + desc)[:700]
        key = text[:80].lower()
        if len(text) < 80 or key in seen:
            continue
        if sev in ("Severe", "Extreme") and len(pos) < PER_SIDE:
            seen.add(key); pos.append({"subject": {"alert": text}, "verdict": "pass"})
        elif sev in ("Minor", "Moderate") and len(neg) < PER_SIDE:
            seen.add(key); neg.append({"subject": {"alert": text}, "verdict": "fail"})
    cands = pos[:PER_SIDE] + neg[:PER_SIDE]
    CAND.write_text(json.dumps(cands, indent=2))
    from collections import Counter
    print("balance:", dict(Counter(c["verdict"] for c in cands)))
    print(f"wrote {len(cands)} candidates -> {CAND}")


def ingest():
    cands = json.loads(CAND.read_text())
    Path(f"state/examples/{SCOPE}/verify.jsonl").unlink(missing_ok=True)
    for c in cands:
        save_example("verify", {"subject": c["subject"], "standard": STANDARD},
                     {"verdict": c["verdict"], "confidence": 1.0, "issues": []}, scope_name=SCOPE)
    print(f"ingested {len(cands)} verify golds -> state/examples/{SCOPE}/verify.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ingest", action="store_true")
    ingest() if ap.parse_args().ingest else harvest()
