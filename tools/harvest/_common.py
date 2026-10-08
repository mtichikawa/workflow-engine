"""Shared harvest helpers: a resilient curl fetch (CDNs block urllib's TLS fingerprint) and a
one-call ingest for CLASSIFY configs. Keeps each domain harvester to a few lines and stops the
ingest logic from drifting across domains. See docs/standards.md.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.examples import save_example


def load_env() -> None:
    """Load the root .env into os.environ (for keyed sources). Does not override already-set vars."""
    envp = Path(__file__).resolve().parents[2] / ".env"
    if not envp.exists():
        return
    for line in envp.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def curl_get(url: str, tries: int = 4, headers: list[str] | None = None, timeout: int = 25) -> str:
    """GET via curl (works where urllib's TLS fingerprint gets 403'd); linear backoff on throttle."""
    # -g: don't treat []{} as globs (bracketed API params); --compressed: decode gzip (e.g. StackExchange)
    cmd = ["curl", "-sSfLg", "--compressed", "--max-time", str(timeout)]
    for h in headers or []:
        cmd += ["-H", h]
    cmd.append(url)
    out = None
    for attempt in range(tries):
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode == 0:
            return out.stdout
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"curl failed after {tries}: {(out.stderr if out else '').strip()[:140]}")


def curl_json(url: str, **kw):
    return json.loads(curl_get(url, **kw) or "{}")


def ingest_classify(scope: str, cands: list[dict], criteria: str) -> tuple[int, list[str]]:
    """Write CLASSIFY golds for a new config. cands = [{"item": {...}, "label": "<real label>"}].
    Categories are derived from the labels actually present (keeps the label space honest). The label
    is real ground truth from the source; only `reasoning` is a factual provenance note, not a judgment."""
    Path(f"state/examples/{scope}/classify.jsonl").unlink(missing_ok=True)   # fresh config
    categories = sorted({c["label"] for c in cands})
    for c in cands:
        save_example(
            "classify",
            {"item": c["item"], "categories": categories, "criteria": criteria},
            {"label": c["label"], "confidence": 1.0,
             "reasoning": f"Ground-truth label from the source catalog: {c['label']}."},
            scope_name=scope,
        )
    from collections import Counter
    print(f"ingested {len(cands)} golds -> state/examples/{scope}/classify.jsonl")
    print("per label:", dict(Counter(c["label"] for c in cands)))
    return len(cands), categories
