"""Composer-drafts-the-gaps — the Composer generates a provisional specialist for a gap.

A drafted specialist is a real, runnable LLM-backed specialist built from a spec
(instruction + contract). It is registered **provisional** (untrusted) and ships with
NO eval — so the Phase-9 convention correctly flags it incomplete until a human
validates it through the gate (gate-as-example-factory). That's the honest boundary:
the Composer DRAFTS (fast, plausible); the human VALIDATES (earns trust); the registry
TRACKS it. Drafts are persisted so later runs can load them.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import registry
from .core import Contract, Specialist, all_specialists, brain, brain_json, register
from .specialists._util import text_of

DRAFT_DIR = Path("state/drafted")


class DraftedSpecialist(Specialist):
    def __init__(self, name, description, input_fields, output_fields, instruction, kind="domain"):
        self.name = name
        self.kind = kind
        self.description = description
        self.tags = ("provisional",)
        self.contract = Contract(input={f: object for f in input_fields},
                                 output={f: object for f in output_fields})
        self._instruction = instruction
        self._out = list(output_fields)

    def _run(self, input, config):
        from .fewshot import block
        fs = block(self.name, input)                    # inject the relevant curated golds, if any
        prompt = f"{self._instruction}\n\n"
        if fs:
            prompt += fs + "\n\n"
        prompt += f"INPUT:\n{text_of(input)}\n\nReturn JSON with exactly these keys: {self._out}."
        r = brain_json(prompt)
        return {f: r.get(f) for f in self._out}


def draft_specialist(gap: dict, use_case: str) -> DraftedSpecialist:
    name = gap["name"]
    in_fields = gap.get("input") or ["item"]
    out_fields = gap.get("output") or ["result"]
    instruction = brain(
        f'Write a concise system instruction (a role) for an AI specialist named "{name}" that, for the '
        f'use case "{use_case}", performs that capability. It receives input fields {in_fields} and must '
        f'produce output fields {out_fields}. In 2-4 sentences, say exactly what it does and how to judge a '
        f"good result. Return only the instruction text."
    ).strip()

    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    (DRAFT_DIR / f"{name}.json").write_text(json.dumps(
        {"name": name, "description": gap.get("why", ""), "input": in_fields,
         "output": out_fields, "instruction": instruction}, indent=2))

    spec = DraftedSpecialist(name, gap.get("why", ""), in_fields, out_fields, instruction)
    register(spec)
    registry.mark_provisional(name)
    return spec


def load_drafted() -> None:
    """Re-instantiate persisted drafts so they're available in fresh processes."""
    if not DRAFT_DIR.exists():
        return
    have = all_specialists()
    for p in DRAFT_DIR.glob("*.json"):
        d = json.loads(p.read_text())
        if d["name"] not in have:
            register(DraftedSpecialist(d["name"], d["description"], d["input"], d["output"], d["instruction"]))
