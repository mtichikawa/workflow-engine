"""Token accounting — log every brain call so we can estimate API cost.

The CLI backend (free on Max) still reports real token counts via
`--output-format json`; we log them so `engine costs` can estimate what the same
work would cost on the billed API. Nothing here bills anything — it's a meter.

    python -m engine.cli costs          # totals + estimated API cost

Prices are LIST prices (USD per 1M tokens) and easy to edit as rates change.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

LOG = Path("state/token_log.jsonl")
# log_call runs inside brain(), which executes on parallel worker threads under
# concurrency > 1 — so the append is serialized (same class of fix as act's _WRITE_LOCK).
_LOG_LOCK = threading.Lock()

# USD per 1,000,000 tokens (input, output). Edit to match current pricing.
PRICES = {
    "opus":   (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku":  (0.80, 4.0),
}
_DEFAULT_TIER = "sonnet"


def _tier(model: str) -> str:
    m = (model or "").lower()
    for k in PRICES:
        if k in m:
            return k
    return _DEFAULT_TIER


def est_usd(in_tok: int, out_tok: int, model: str) -> float:
    pin, pout = PRICES[_tier(model)]
    return (in_tok or 0) / 1e6 * pin + (out_tok or 0) / 1e6 * pout


def log_call(model: str, provider: str, in_tok: int, out_tok: int,
             tag: str = "", cli_cost: float | None = None) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": round(time.time()), "provider": provider, "model": model or "",
           "in": in_tok or 0, "out": out_tok or 0, "tag": tag}
    if cli_cost is not None:
        rec["cli_cost"] = cli_cost
    with _LOG_LOCK, LOG.open("a") as fh:               # serialized: concurrent brain calls append safely
        fh.write(json.dumps(rec) + "\n")


def summary() -> dict:
    if not LOG.exists():
        return {"calls": 0, "in": 0, "out": 0, "est_usd": 0.0, "cli_cost": 0.0, "by_tag": {}}
    calls = tin = tout = 0
    est = cli = 0.0
    by_tag: dict[str, dict] = {}
    for line in LOG.open():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        calls += 1
        tin += r["in"]
        tout += r["out"]
        est += est_usd(r["in"], r["out"], r["model"])
        cli += r.get("cli_cost") or 0.0
        t = by_tag.setdefault(r.get("tag") or "—", {"calls": 0, "in": 0, "out": 0, "est_usd": 0.0})
        t["calls"] += 1
        t["in"] += r["in"]
        t["out"] += r["out"]
        t["est_usd"] += est_usd(r["in"], r["out"], r["model"])
    return {"calls": calls, "in": tin, "out": tout, "est_usd": est, "cli_cost": cli, "by_tag": by_tag}
