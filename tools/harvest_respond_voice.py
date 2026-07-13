"""Build RESPOND's UNIVERSAL BASELINE from real, identity-stripped maintainer replies.

Not impersonation: we keep only the WORDS (the craft of a good technical reply — open on the
problem, ask for the specific missing thing, no fluff), never a name. We pull from SEVERAL
respected repos and blend, so no single person's voice dominates — what emerges is a composite
"good technical reply" style, which is generic and reusable (a universal baseline per design
decision #7), not a per-customer voice.

    python examples/harvest_respond_voice.py            # harvest -> candidates file
    python examples/harvest_respond_voice.py --ingest    # write curated golds

Harvest is heuristic (find issues where a maintainer left a substantive first reply); the human
still curates which candidates become golds. We over-fetch and filter so nothing verbatim-echoes
one individual.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.examples import save_example, EX_DIR

# Repos chosen for strong, public, well-regarded maintainer reply culture. Blend across all —
# cap per-source so no single voice dominates the baseline.
REPOS = ["sindresorhus/got", "simonw/datasette", "tiangolo/fastapi",
         "yargs/yargs", "pallets/click"]
CAND = Path("state/review/respond_candidates.json")

MIN_REPLY = 220           # a substantive reply, not "thanks, fixed"
MAX_REPLY = 1100          # keep it first-reply sized
PER_REPO_CAP = 4          # blend cap — no single source dominates


def _gh(path: str) -> list | dict:
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {out.stderr.strip()[:160]}")
    return json.loads(out.stdout or "[]")


def _strip_identity(text: str) -> str:
    """Remove @-mentions and obvious name signatures; keep the words."""
    text = re.sub(r"\r", "", text)
    text = re.sub(r"@[A-Za-z0-9_-]+", "someone", text)              # @handle -> someone
    text = re.sub(r"^(?:\s*(?:hi|hey|hello|thanks|thank you)?[, ]*someone[, ]*)+", "", text,
                  flags=re.IGNORECASE)                             # drop leading "someone" greetings
    text = re.sub(r"\bsomeone(\s+someone)+\b", "someone", text)     # collapse runs
    return text.strip()


def _looks_like_reply(body: str) -> bool:
    b = body.strip()
    if not (MIN_REPLY <= len(b) <= MAX_REPLY):
        return False
    low = b.lower()
    if low.startswith(("duplicate of", "closing", "fixed in", "released in", "see #")):
        return False
    if "```" in b and b.count("```") > 2:      # skip long code dumps — we want prose replies
        return False
    return True


def harvest() -> list[dict]:
    candidates = []
    for repo in REPOS:
        owner = repo.split("/")[0]
        kept = 0
        try:
            issues = _gh(f"repos/{repo}/issues?state=all&per_page=30&sort=comments&direction=desc")
        except Exception as e:  # noqa: BLE001
            print(f"  ({repo}: skipped — {e})")
            continue
        for iss in issues:
            if kept >= PER_REPO_CAP or "pull_request" in iss or (iss.get("comments") or 0) < 1:
                continue
            num = iss["number"]
            try:
                comments = _gh(f"repos/{repo}/issues/{num}/comments?per_page=10")
            except Exception:  # noqa: BLE001
                continue
            opener = iss.get("user", {}).get("login")
            for c in comments:                            # first substantive reply from someone else
                author = c.get("user", {}).get("login", "")
                body = c.get("body") or ""
                # a maintainer-ish reply: not the opener, association OWNER/MEMBER/COLLABORATOR
                assoc = c.get("author_association", "")
                if author != opener and assoc in ("OWNER", "MEMBER", "COLLABORATOR") and _looks_like_reply(body):
                    candidates.append({
                        "source": owner,
                        "issue": {"title": iss.get("title", ""),
                                  "body": _strip_identity((iss.get("body") or "")[:1200])},
                        "reply": _strip_identity(body),
                    })
                    kept += 1
                    break
        print(f"  {repo}: {kept} candidate reply(ies)")
    CAND.parent.mkdir(parents=True, exist_ok=True)
    CAND.write_text(json.dumps(candidates, indent=2))
    print(f"\nwrote {len(candidates)} candidates -> {CAND}")
    print(f"blend: {dict(Counter(c['source'] for c in candidates))}")
    return candidates


def ingest():
    if not CAND.exists():
        sys.exit("no candidates — run without --ingest first.")
    cands = json.loads(CAND.read_text())
    (EX_DIR / "respond.jsonl").unlink(missing_ok=True)     # fresh baseline
    tone = ("a sharp, warm senior maintainer: concise and specific, engage the actual problem, "
            "ask for exactly what's missing, promise nothing")
    n = 0
    for c in cands:
        save_example("respond", {"item": c["issue"], "tone": tone}, {"reply": c["reply"]})
        n += 1
    print(f"ingested {n} RESPOND golds (identity-stripped, blended) -> state/examples/respond.jsonl")
    print(f"blend: {dict(Counter(c['source'] for c in cands))}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true", help="write curated candidates as golds")
    args = ap.parse_args()
    ingest() if args.ingest else harvest()
