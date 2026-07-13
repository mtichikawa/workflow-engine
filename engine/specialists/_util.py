"""Small helpers shared by specialists: stringify items, coerce model output."""

from __future__ import annotations

import json


def text_of(item, limit: int = 4000) -> str:
    """Render a work-item (dict or str) into text for a prompt."""
    if isinstance(item, str):
        s = item
    elif isinstance(item, dict):
        s = "\n".join(f"{k}: {v}" for k, v in item.items() if v not in (None, ""))
    else:
        s = json.dumps(item, default=str)
    return s[:limit]


def num(x, default: float = 0.5) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def as_list(x) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def one_sentence(x) -> str:
    return str(x or "").strip().replace("\n", " ")
