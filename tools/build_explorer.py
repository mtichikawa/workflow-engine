"""Regenerate a use-case explorer from its recipe + a real run log — no hand-editing.

    python tools/build_explorer.py triage        # writes usecases/triage/index.html

The card content, graph structure, sockets, wires, and gate/loop edges are all derived
(engine/explorer.py): structure from the recipe, values + reasoning verbatim from the run log,
the per-specialist blurbs written once. Only the per-use-case knobs live here — the work-item
noun, the title, the one-line description, and which run/item to show.
"""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.explorer import build_html, load_run

SPECS = {
    "triage": {
        "recipe": "engine.recipes.triage:TRIAGE",
        "run": "examples/full_run/triage-nextjs-95698/run.json",
        "item": "95698",
        "work_item": "issue",
        "title": "Triage",
        "desc": "Watch one incoming <em>GitHub issue</em> get sorted, prioritized, routed, answered, "
                "checked — then staged for a human. Click any card to see what it does.",
    },
    "content": {
        "recipe": "engine.recipes.content:CONTENT",
        "run": "examples/full_run/content-flaky-tests/run.json",
        "item": "topic",
        "work_item": "topic",
        "title": "Content",
        "desc": "Takes a <em>topic</em>: pulls sources, picks an angle, writes a short post in a set voice, "
                "checks it's on-brand, and stages it. Reuses triage's specialists — only <em>write</em> is new.",
    },
    "refine": {
        "recipe": "engine.recipes.refine:REFINE",
        "run": "examples/full_run/refine-loop/run.json",
        "item": "topic",
        "work_item": "brief",
        "title": "Refine",
        "desc": "Drafts, grades itself against a strict bar, and rewrites until it passes — then waits for a "
                "human. The <em>loop</em> is the point — data flows back through write ↔ verify.",
    },
    "triage-requests": {
        "recipe": "engine.recipes.triage:TRIAGE",
        "run": "examples/full_run/triage-requests/run.json",
        "item": "7574", "work_item": "issue", "title": "Triage \u00b7 psf/requests",
        "desc": "The same triage workflow on a <em>different repo entirely</em> \u2014 real open issues from psf/requests, sorted, prioritized, routed, answered, staged.",
    },
    "content-oncall": {
        "recipe": "engine.recipes.content:CONTENT",
        "run": "examples/full_run/content-oncall/run.json",
        "item": "topic", "work_item": "topic", "title": "Content \u00b7 on-call",
        "desc": "A different topic \u2014 <em>why on-call rotations burn people out</em>: pulls sources, picks an angle, writes it in-voice, checks it's on-brand, stages it.",
    },
    "refine-codereview": {
        "recipe": "engine.recipes.refine:REFINE",
        "run": "examples/full_run/refine-codereview/run.json",
        "item": "topic", "work_item": "brief", "title": "Refine \u00b7 code review",
        "desc": "A different topic through the loop \u2014 <em>why code review culture matters</em>: draft, self-grade, rewrite until it clears the bar.",
    },
}


def _load(ref):
    mod, name = ref.split(":")
    return getattr(importlib.import_module(mod), name)


def build(slug):
    s = SPECS[slug]
    recipe = _load(s["recipe"])
    run = load_run(str(ROOT / s["run"]))
    html = build_html(recipe, run, work_item=s["work_item"], title=s["title"],
                      desc=s["desc"], item_id=s.get("item"),
                      template=str(ROOT / "engine" / "explorer_engine.html"))
    out = ROOT / "usecases" / slug / "index.html"
    out.write_text(html)
    print(f"wrote {out.relative_to(ROOT)}  ({len(html)} bytes)")


if __name__ == "__main__":
    for slug in (sys.argv[1:] or SPECS.keys()):
        build(slug)
