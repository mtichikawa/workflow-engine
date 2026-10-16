"""Composer — a recipe that writes recipes.

Given a plain-English use case and the specialist catalog, it decomposes the work,
selects library specialists, DRAWS THE EDGES (branches / loops / joins), assembles a
Recipe, and FLAGS GAPS where a new domain-specialist is needed. It runs its own output
through the Validator and repairs on errors — a compile-error loop, so an LLM doesn't
have to be right first try, only right after feedback.
"""

from __future__ import annotations

import json

from .core import Edge, Recipe, Step, all_specialists, brain_json, validate
from .registry import catalog
from .specialists import CAPABILITIES

PROMPT = """You are the Composer. Assemble a RECIPE for this use case:
"{use_case}"

Available specialists (the library):
{catalog}

Rules:
- A recipe runs per work-item. Each work-item's input is available as `payload` (a dict; the text of the
  item is at `payload.text`).
- Each step is: {{"id","specialist","config":{{...}},"inputs":{{field:source}},"gate":bool}}, plus "each" for a
  step that runs once per element of a list (below).
- CRITICAL — `config` vs `inputs`:
    * `config` = STATIC values YOU choose now: category lists, criteria/scoring/standard/checklist text,
      target, mode, tone. Fill every static field a specialist needs.
    * `inputs` = ONLY source expressions pulling live data: "payload", "payload.KEY", "STEP_ID",
      "STEP_ID.KEY". Never put a literal list/string in `inputs`; never put a source expression in `config`.
- Example step: {{"id":"categorize","specialist":"classify",
    "config":{{"categories":["billing","technical","account","other"],"criteria":"the topic"}},
    "inputs":{{"item":"payload.text"}}}}
- REUSE the shared capability-specialists (fetch, classify, rank, verify, act) for the bookends.
- REUSE-FIRST: read each specialist's "does" card (it states USE WHEN / NOT / and whether it is
  CONFIG-DRIVEN). Before proposing a NEW specialist, check whether an existing config-driven capability's
  contract fits the step with a different `config` -- ANY categorization is `classify` with new
  categories; ANY 0..1 scoring is `rank`; ANY pass/fail-vs-a-bar is `verify`. Do NOT clone a capability
  per domain (no "art_classifier", "cuisine_classifier" -- that is `classify` with a config).
- Only when NO existing capability's contract fits the step's KIND of judgment: add the step (clear
  snake_case name) AND list it under "gaps" with a proposed input/output.
- FOR EACH: when the work covers several things inside ONE work-item (each line item in a note, each paragraph,
  each ticket returned by one MCP call), do NOT invent a specialist for the iteration. First produce the list
  (extract → "STEP.items", fetch → "STEP.items", an mcp_call → "STEP.result", or "payload.KEY"), then give the
  per-thing step "each": "<that list>". Its inputs read the current element as "each" (or "each.KEY"); its
  output is {{"results":[one output per element],"count":n}}, read later as "STEP_ID.results". Example:
  {{"id":"label_lines","specialist":"classify","each":"lines.items","inputs":{{"item":"each"}},
    "config":{{"categories":["travel","meals","supplies"],"criteria":"the GL category"}}}}
  (Many things handed in separately — CSV rows, files in a folder, pasted messages — are already one work-item
  each: no "each" needed.)
- WHOLE-LIST judgments are existing capabilities fed the whole list, not new specialists: dedupe, group, or
  "which have no match" → extract with a target that says exactly what to return ("the distinct tools, merging
  names for the same thing", "transactions with no matching ledger entry"; its text may be a list or several
  texts); the biggest issue / an overview → summarize; an order → sequence; are-these-two-the-same → match.
- Loops are capped automatically at a few passes — never add a counter step.
- OUTSIDE SYSTEMS: use mcp_call only for an MCP server the request NAMES. If the work needs another system
  (Slack, Jira, a database, QuickBooks, analytics, web search or scraping) and names no MCP server, list it
  under "gaps" (e.g. "slack_post: no MCP server named for Slack") — don't plan a call to a server you assumed.
- HOW ITEMS ARRIVE is not a step and never a gap: a webhook, a folder, a CSV or JSONL file, a pasted batch, or
  a schedule is chosen when the workflow is saved, and each arriving thing becomes one work-item (`payload`).
- WHAT THE LIBRARY CAN READ: text only. No specialist here looks at images, photos, scans or handwriting, and
  none hears audio or video (a podcast, a voicemail) — work that needs those is a gap.
- Simple measurable standards (a length limit, required words present) are a `verify` standard, not a new
  specialist.
- Any contract field may be wired from live data in `inputs` when it must vary per item (e.g. verify's standard
  taken from the reference document).
- Every step's output should be USED by a later input or condition (don't add steps whose result nothing reads).
- Include an `act` step ONLY when the use case has a real external side-effect (post/save/send). If the output
  itself is the deliverable (a ranking, a verdict, a summary), END there — no `act`. When you DO include `act`:
    config {{"target":"file","mode":"staged"}} with inputs {{"payload":{{"content":"<source>","name":"result.txt"}}}}
    (or target "github" with payload {{"labels":[...],"comment":"<source>","url":"payload.url"}}).

CONTROL FLOW (optional): by default the steps run in the order you list them (linear). To add a branch, loop,
or join, ALSO return an "edges" list. Each edge is {{"from","to","when"}} ("when" optional):
  * branch — two edges out of one step with different `when` conditions;
  * loop  — an edge whose "to" is an EARLIER step, with a `when` that can eventually become false;
  * join  — two edges into one step; set that step's "join":"and" (wait for all) or "or" (first).
A `when` is a simple condition over a prior step's output, e.g. "verify.verdict == 'pass'",
"classify.label == 'spam'", "check.score > 0.5".
- NO DEAD-ENDS: never leave a work-item with nowhere to go. Whenever you branch on a step's output (any
  conditional edge), cover every outcome — the else/negative case must have a path too: loop it back to
  revise, or route it forward (e.g. still stage a flagged item for a human). Don't stop at a lone guarded
  edge with no other branch. (A check that can fail is the usual place this gets forgotten.)
Omit "edges" for a linear recipe.

Return JSON: {{"steps":[...], "edges":[...], "gaps":[{{"name","why","input":[...],"output":[...]}}]}}"""


def compose(use_case: str, draft: bool = False, max_repairs: int = 2, progress=None) -> dict:
    """`progress`, if given, is called with each stage as it happens — {"stage": "draft" | "repair", "attempt"}
    before a model call, then {"stage": "valid", "attempt", "steps"} or {"stage": "invalid", "attempt",
    "errors"} after the validator — so a screen can show the compile-error loop instead of a spinner."""
    say = progress or (lambda event: None)
    base = PROMPT.format(use_case=use_case, catalog=json.dumps(catalog(), indent=1))
    prompt, data = base, {}
    for attempt in range(1, max_repairs + 2):
        say({"stage": "draft" if attempt == 1 else "repair", "attempt": attempt})
        data = brain_json(prompt)
        steps, edges = _steps(data), _edges(data)
        if not steps:
            say({"stage": "invalid", "attempt": attempt, "errors": ["the draft has no steps"]})
            break
        errs = [f for f in validate(Recipe("composed", steps, edges), check_contracts=False)
                if f.level == "error"]
        say({"stage": "invalid", "attempt": attempt, "errors": [f.msg for f in errs]} if errs
            else {"stage": "valid", "attempt": attempt, "steps": len(steps)})
        if not errs:
            break
        prompt = base + _repair(data, errs)                 # compile-error feedback loop

    steps, edges = _steps(data), _edges(data)
    have = set(all_specialists())
    missing = sorted({s.specialist for s in steps if s.specialist not in have})

    drafted = []
    if draft and missing:
        from .drafting import draft_specialist
        gaps_by_name = {g.get("name"): g for g in data.get("gaps", [])}
        for name in missing:
            gap = gaps_by_name.get(name, {"name": name, "input": ["item"], "output": ["result"]})
            drafted.append(draft_specialist(gap, use_case).name)
        have = set(all_specialists())
        missing = sorted({s.specialist for s in steps if s.specialist not in have})

    recipe = Recipe("composed", steps, edges) if steps else None
    findings = validate(recipe) if recipe else []
    errors = [str(f) for f in findings if f.level == "error"]
    return {
        "recipe": recipe,
        "steps": data.get("steps", []),
        "edges": data.get("edges", []),
        "gaps": data.get("gaps", []),
        "missing": missing,
        "drafted": drafted,
        "findings": findings,
        "errors": errors,
        "runnable": not missing and not errors,
    }


def _steps(data) -> list[Step]:
    return [Step(id=s["id"], specialist=s["specialist"], config=s.get("config", {}),
                 inputs=s.get("inputs", {}), gate=s.get("gate", False),
                 join=s.get("join", "and"), each=s.get("each") or None,
                 domain=s["specialist"] not in CAPABILITIES)
            for s in data.get("steps", []) if s.get("id") and s.get("specialist")]


def _edges(data) -> list[Edge]:
    return [Edge(e["from"], e["to"], e.get("when"))
            for e in data.get("edges", []) if e.get("from") and e.get("to")]


def _repair(data, errors) -> str:
    return ("\n\nYour previous attempt was INVALID. Fix these errors and return corrected JSON:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\n\nYour previous steps + edges were:\n"
            + json.dumps({"steps": data.get("steps", []), "edges": data.get("edges", [])}, indent=1))
