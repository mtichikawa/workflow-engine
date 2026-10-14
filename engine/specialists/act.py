"""act — capability specialist: write to an external system, behind a gate.

`mode="staged"` (the proof default) NEVER publishes — it produces exactly what WOULD
be sent and records it, so a stranger's repo is never touched. `mode="live"` is where
real posting would go (not used in the proof). Reused by both recipes.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from ..core import Contract, Specialist

# `act` is the one specialist with real side effects (file writes), and it can run on
# parallel worker threads — so its writes are serialized. Every other specialist is pure.
_WRITE_LOCK = threading.Lock()


class Act(Specialist):
    name = "act"
    kind = "capability"
    description = (
        "Stage an external side-effect (post/label/comment/save) BEHIND A HUMAN GATE -- never sends "
        "without approval. USE WHEN a recipe must DO something outside itself. It can ONLY write a staged "
        "file or stage a GitHub label/comment: it CANNOT send email, SMS or faxes, pay, call, or post anywhere "
        "else -- a request that needs those has a GAP (name it), even with a person approving first. "
        "NOT when the deliverable is the output itself (a ranking/verdict/summary) -- end there. "
        "CONFIG-DRIVEN via {target (github|file), mode (staged)}. IN target,payload,mode -> OUT status,result."
    )
    side_effect = True
    contract = Contract(
        input={"target": str, "payload": object, "mode": str},
        output={"status": str, "result": dict},
    )

    def _run(self, input, config):
        target, payload, mode = input["target"], input["payload"], input["mode"]
        out_dir = Path(config.get("out_dir", "output"))
        out_dir.mkdir(parents=True, exist_ok=True)

        if mode != "staged":
            raise ValueError("act: only mode='staged' is enabled in the proof (no live posting)")

        if target == "github":
            result = {"would_post": {"labels": payload.get("labels", []),
                                     "comment": payload.get("comment", "")},
                      "on": payload.get("url", "")}
        elif target == "file":
            name = os.path.basename(payload.get("name") or "post.txt")   # basename -> no path traversal
            with _WRITE_LOCK:
                (out_dir / name).write_text(str(payload.get("content", "")))
            result = {"wrote": str(out_dir / name)}
        else:
            raise ValueError(f"act: unknown target '{target}'")

        if isinstance(payload, dict):                # carry any extra fields (priority, angle…) through
            extra = {k: v for k, v in payload.items()
                     if k not in ("labels", "comment", "url", "content", "name")}
            if extra:
                result["meta"] = extra

        with _WRITE_LOCK, (out_dir / "staged.jsonl").open("a") as fh:     # closed + serialized
            fh.write(json.dumps({"target": target, "result": result}, default=str) + "\n")
        return {"status": "staged", "result": result}
