"""Board — the durable, multi-item hopper.

You feed work-items in; the board holds many in flight at once, each flowing through
the recipe's steps. Model A (one item) and Model B (many) are the same structure.
Crash-safe: everything is persisted, and the dispatcher reconciles from it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATUSES = ("todo", "ready", "running", "blocked", "gated", "skipped", "done", "failed")


@dataclass
class Card:
    item_id: str
    step_id: str
    status: str = "todo"
    input: dict | None = None
    output: dict | None = None
    attempts: list = field(default_factory=list)
    visits: int = 0                      # how many times this step has run (loop counter)
    coverage: dict | None = None         # few-shot layer split (tailored vs baseline) when a tenant scope is active


class Board:
    def __init__(self, recipe: str, run_id: str, state_dir: str | Path = "state"):
        self.recipe = recipe
        self.run_id = run_id
        self.items: dict[str, dict] = {}                    # item_id -> {payload, status}
        self.cards: dict[tuple, Card] = {}                  # (item_id, step_id) -> Card
        self.context: dict[str, dict] = {}                  # item_id -> {step_id: output}
        self.events: list[dict] = []                        # ordered transitions, for replay
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / f"{run_id}.json"

    # ---- items / cards --------------------------------------------------
    def add_item(self, item_id: str, payload: dict) -> None:
        self.items[item_id] = {"payload": payload, "status": "open"}
        self.context.setdefault(item_id, {})

    def add_card(self, item_id: str, step_id: str, status: str = "todo") -> Card:
        card = Card(item_id=item_id, step_id=step_id, status=status)
        self.cards[(item_id, step_id)] = card
        return card

    def card(self, item_id: str, step_id: str) -> Card | None:
        return self.cards.get((item_id, step_id))

    def cards_for(self, item_id: str) -> list[Card]:
        return [c for (i, _), c in self.cards.items() if i == item_id]

    def with_status(self, *statuses: str) -> list[Card]:
        return [c for c in self.cards.values() if c.status in statuses]

    def record_output(self, item_id: str, step_id: str, output: dict) -> None:
        self.context.setdefault(item_id, {})[step_id] = output

    def log_event(self, item_id: str, step_id: str, status: str) -> None:
        self.events.append({"n": len(self.events), "item": item_id, "step": step_id, "status": status})

    # ---- persistence ----------------------------------------------------
    def save(self) -> None:
        data = {
            "recipe": self.recipe,
            "run_id": self.run_id,
            "items": self.items,
            "context": self.context,
            "cards": [asdict(c) for c in self.cards.values()],
            "events": self.events,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.replace(self.path)          # atomic write — crash-safe

    @classmethod
    def load(cls, run_id: str, state_dir: str | Path = "state") -> "Board":
        path = Path(state_dir) / f"{run_id}.json"
        data = json.loads(path.read_text())
        b = cls(data["recipe"], run_id, state_dir)
        b.items = data["items"]
        b.context = data.get("context", {})
        b.events = data.get("events", [])
        for c in data["cards"]:
            b.cards[(c["item_id"], c["step_id"])] = Card(**c)
        return b

    # ---- a compact snapshot for the trace / a board view ----------------
    def snapshot(self) -> dict[str, list[str]]:
        cols: dict[str, list[str]] = {s: [] for s in STATUSES}
        for c in self.cards.values():
            cols[c.status].append(f"{c.item_id}:{c.step_id}")
        return {k: v for k, v in cols.items() if v}
