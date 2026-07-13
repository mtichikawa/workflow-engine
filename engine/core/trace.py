"""Run trace — the dispatcher emits every state transition.

Near-free (the board already records everything) and doubles as the minimal
presentation layer: a readable play-by-play of specialists coordinating.
"""

from __future__ import annotations

import json
from pathlib import Path


class Tracer:
    def __init__(self, run_id: str, log_dir: str | Path = "logs", echo: bool = True):
        self.run_id = run_id
        self.echo = echo
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.log_dir / f"{run_id}.log"

    def event(self, kind: str, msg: str = "", **fields) -> None:
        line = f"[{self.run_id}] {kind:<10} {msg}"
        if fields:
            line += "  " + " ".join(f"{k}={_short(v)}" for k, v in fields.items())
        if self.echo:
            print(line, flush=True)
        with self.path.open("a") as fh:
            fh.write(line + "\n")


def _short(v, n: int = 60) -> str:
    if isinstance(v, (dict, list)):
        v = json.dumps(v, default=str)
    s = str(v).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"
