"""Generate a use-case explorer's card data from (recipe + run log) — no hand-curation.

The whole point: a card's content is never authored per use case. Only ~7 things are hand-written,
once ever — each specialist's display template below (its `specialty` line, how to phrase its `config`
as the `tuned` line, and how to phrase its logged `output` as the `this <item>` line). Everything else
comes from the recipe (structure, config) and the run log (values + the specialist's own reasoning,
verbatim). New recipes reuse these templates as-is.

    cards = generate_cards(TRIAGE, load_run("state/triage-....json"), item_id="95698")

Each card: {id, specialty, tuned, out}. `out` is a dict {value, why, full} where `value` is the short
result (shown highlighted), `why` is the specialist's own reasoning verbatim, and `full` is the long
free-text output (e.g. a drafted reply) for the truncate-and-expand affordance — never summarized by us.
"""

from __future__ import annotations

import html as _html
import json


def _join(xs):
    return " · ".join(xs)


# ── the ONLY hand-written text in the system: one template per specialist, written once, reused everywhere ──
BLURBS = {
    "classify": {
        "specialty": "sorting an item into one category",
        "tuned": lambda c: f"here, into: {_join(c['categories'])}",
        "out":   lambda o: {"value": f"{o['label']} ({o['confidence']})", "why": o.get("reasoning", "")},
    },
    "rank": {
        "specialty": "scoring how urgent an item is, 0 to 1",
        "tuned": lambda c: f"here, by the rule — {c['scoring']}",
        "out":   lambda o: {"value": str(o["score"]), "why": o.get("reasoning", "")},
    },
    "route": {
        "specialty": "picking the one owner an item belongs to",
        "tuned": lambda c: f"here, from: {_join(c['components'])}",
        "out":   lambda o: {"value": o["component"], "why": o.get("reasoning", "")},
    },
    "respond": {
        "specialty": "drafting a first reply",
        "tuned": lambda c: f"here, {c['tone']}",
        "out":   lambda o: {"value": "a drafted reply", "full": o["reply"]},   # long → truncate+expand
    },
    "verify": {
        "specialty": "checking whether a set of results holds together",
        "tuned": lambda c: f"here, {c['standard']}",
        "out":   lambda o: {"value": f"{o['verdict']} ({o.get('confidence','')})".strip(),
                            "why": "raised " + str(len(o.get("issues", []))) + " concern(s): " + "  •  ".join(o.get("issues", [])) if o.get("issues") else "no concerns"},
    },
    "act": {
        "specialty": "staging an action for a human to approve",
        "tuned": lambda c: f"here, {c['mode']} mode — never posts to {c['target']} automatically",
        "out":   lambda o: {"value": o.get("status", "staged"),
                            "why": "would apply labels " + str(o.get("result", {}).get("would_post", {}).get("labels", [])) + " and post the reply"},
    },
    "fetch": {
        "specialty": "pulling in source material to work from",
        "tuned": lambda c: "",                                  # no config — behaves the same everywhere
        "out":   lambda o: {"value": f"{len(o.get('items', []))} sources", "why": ""},
    },
    "write": {
        "specialty": "writing a short post",
        "tuned": lambda c: "",
        "out":   lambda o: {"value": "a drafted post", "full": o.get("post", "")},
    },
}


def load_run(path):
    with open(path) as f:
        return json.load(f)


# ── (1) structure: derive nodes / sockets / wires from the recipe (no hand-typing) ──
def _leaves(inputs):
    """Flatten a step's inputs to (leaf_key, ref) — ref is a source string or a list of them."""
    for k, v in inputs.items():
        if isinstance(v, dict):
            yield from _leaves(v)
        else:
            yield k, v


def _ref_src(ref, step_ids, work_item):
    """A single source expression -> (node_id, output_socket), or None for a literal."""
    head, _, field = ref.partition(".")
    if head == "payload":
        return "IN", (field or work_item)
    if head in step_ids:
        return head, (field or "output")
    return None


def build_graph(recipe, work_item="item"):
    """Nodes + wires for the explorer, straight from the recipe. Kinds from step flags, columns from
    the data-flow depth, sockets from inputs/reads, wires from inputs (data) and edges (control)."""
    step_ids = {s.id for s in recipe.steps}
    kind = lambda s: "gate" if s.gate else "domain" if s.domain else "shared"
    order = {s.id: i for i, s in enumerate(recipe.steps)}
    is_back = lambda a, b: a in order and b in order and order[a] > order[b]   # a->b references an earlier step = a loop (feedback)

    wires, outs, ins = [], {"IN": []}, {}
    for s in recipe.steps:
        ins[s.id], outs[s.id] = [], []
    def add_out(nid, sock):
        if sock not in outs.setdefault(nid, []):
            outs[nid].append(sock)

    # data wires from every step's inputs; input-socket name is the work_item noun when it reads the whole payload
    for s in recipe.steps:
        for key, ref in _leaves(s.inputs):
            refs = ref if isinstance(ref, list) else [ref]
            whole = all(r == "payload" for r in refs)
            in_sock = work_item if whole else key
            if in_sock not in ins[s.id]:
                ins[s.id].append(in_sock)
            for r in refs:
                src = _ref_src(r, step_ids, work_item)
                if not src:
                    continue
                add_out(src[0], src[1])
                wires.append({"src": src[0], "srcSock": src[1], "dst": s.id, "dstSock": in_sock,
                              "type": "loop" if is_back(src[0], s.id) else "data"})

    # control wires (guarded edges): forward = gate, backward = loop. dst gets a gate socket.
    for e in recipe.edges:
        if not (e.when and e.when.strip()):
            continue
        head = e.when.split(".")[0].split()[0]
        field = e.when.split(".")[1].split()[0].strip("' \"()") if "." in e.when else "output"
        add_out(e.src, field)
        gate_sock = "when " + e.when.split("==")[-1].strip().strip("'\" ") if "==" in e.when else "gate"
        if gate_sock not in ins.setdefault(e.dst, []):
            ins[e.dst].insert(0, gate_sock)
        wires.append({"src": e.src, "srcSock": field, "dst": e.dst, "dstSock": gate_sock,
                      "type": "loop" if recipe.is_backward(e) else "gate", "when": e.when})

    # terminal steps feed OUT
    has_fwd = {e.src for e in recipe.edges if not recipe.is_backward(e)}
    ins["OUT"] = ["result"]
    for s in recipe.steps:
        if s.id not in has_fwd:
            add_out(s.id, "result")
            wires.append({"src": s.id, "srcSock": "result", "dst": "OUT", "dstSock": "result", "type": "data"})

    # columns = longest path from IN over data + forward-control wires
    col = {"IN": 0, "OUT": None}
    for s in recipe.steps:
        col[s.id] = 0
    changed = True
    while changed:
        changed = False
        for w in wires:
            if w["dst"] == "OUT" or w["type"] == "loop":        # loop (backward) edges must not drive columns forward → no cycle
                continue
            if col.get(w["dst"], 0) < col.get(w["src"], 0) + 1:
                col[w["dst"]] = col[w["src"]] + 1
                changed = True
    col["OUT"] = max(v for k, v in col.items() if k != "OUT") + 1

    nodes = [{"id": "IN", "kind": "in", "col": 0, "outs": outs["IN"], "ins": []}]
    for s in recipe.steps:
        nodes.append({"id": s.id, "kind": kind(s), "col": col[s.id],
                      "outs": outs[s.id], "ins": ins[s.id], "gate": bool(s.gate)})
    nodes.append({"id": "OUT", "kind": "out", "col": col["OUT"], "outs": [], "ins": ins["OUT"]})
    return {"nodes": nodes, "wires": wires, "work_item": work_item}


def generate_cards(recipe, run, item_id=None):
    """One card per specialist step: {id, specialist, specialty, tuned, out} — all derived, none authored here."""
    if item_id is None:
        item_id = next(iter(run["items"]))
    by_step = {c["step_id"]: c for c in run["cards"] if c["item_id"] == item_id}
    cards = []
    for step in recipe.steps:
        b = BLURBS.get(step.specialist)
        if not b:
            continue
        logged = by_step.get(step.id, {})
        out = logged.get("output", {})
        atts = logged.get("attempts", [])
        card = {
            "id": step.id,
            "specialist": step.specialist,
            "specialty": b["specialty"],
            "tuned": b["tuned"](step.config or {}),
            "out": b["out"](out) if out else {"value": "(no run data)", "why": ""},
            "history": [b["out"](a["output"]) for a in atts if a.get("output")],   # per-pass (>1 = it looped)
        }
        cards.append(card)
    return cards


# ── (2) merge content into structure, then inject into the engine template ──
def _fmt_out(out, work_item):
    val = _html.escape(str(out.get("value", "")))
    if out.get("full"):                                         # long free-text: preview + click-to-expand full (verbatim, not summarized)
        prev = _html.escape(out["full"][:150].rstrip())
        return (f'→ {val}: <span class="q">“{prev}…”</span> '
                f'<span class="rmore">show full ▸</span>'
                f'<div class="rfull">{_html.escape(out["full"])}</div>')
    return f'→ <span class="q">{val}</span> — {_html.escape(str(out.get("why", "")))}'


def _fmt_history(history, work_item):    # a looped step: show each pass, using the same per-specialist formatter
    rows = "".join(f'<div class="pass"><span class="pn">pass {i}</span> {_fmt_out(o, work_item)}</div>'
                   for i, o in enumerate(history, 1))
    return f'<span class="q">{len(history)} passes</span> — drafted, checked, and revised until it passed:{rows}'


def _raw(run, item_id, step_id):
    c = next((c for c in run["cards"] if c["item_id"] == item_id and c["step_id"] == step_id), {})
    return c.get("output", {})


def _headline(payload):
    """The human-readable identifier of a work item — for any payload shape."""
    for k in ("title", "topic", "subject", "name", "question", "text"):
        if payload.get(k):
            return payload.get("id"), str(payload[k])
    strs = [(k, v) for k, v in payload.items() if isinstance(v, str) and v]
    return payload.get("id"), (max(strs, key=lambda kv: len(kv[1]))[1] if strs else "")


def _short(v, n=44):
    s = str(v)
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def build_data(recipe, run, work_item, title, desc, item_id=None):
    """Full node list (structure + content) + header — everything the engine needs, all derived."""
    if item_id is None:
        item_id = next(iter(run["items"]))
    g = build_graph(recipe, work_item)
    cards = {c["id"]: c for c in generate_cards(recipe, run, item_id)}
    payload = run["items"][item_id]["payload"]

    for n in g["nodes"]:
        if n["id"] in cards:                                    # a specialist
            c = cards[n["id"]]
            detail = [["specialty", c["specialty"]]]
            if c["tuned"]:                                       # config-less specialists (fetch/write) skip the tuned row
                detail.append(["tuned", c["tuned"]])
            looped = len(c.get("history", [])) > 1               # step ran more than once → show the pass-by-pass trail
            detail.append([f"this {work_item}", _fmt_history(c["history"], work_item) if looped else _fmt_out(c["out"], work_item)])
            n["detail"] = detail
        elif n["kind"] == "in":
            iid, head = _headline(payload)
            fields = " · ".join(k for k in payload if k not in ("id", "status", "payload"))
            n.update(title=f"the {work_item}", w0=250,
                     sub=(f"#{iid} · " if iid else "") + f'“{_short(head, 60)}”',
                     detail=[["what", f"the raw work item the whole recipe runs on — one incoming {work_item}"],
                             ["carries", fields],
                             [f"this {work_item}", (f"#{iid} — " if iid else "") + f'<span class="q">“{_html.escape(head)}”</span>']])
        elif n["kind"] == "out":                                # summarize what the terminal step(s) staged — generic
            term = [w["src"] for w in g["wires"] if w["dst"] == "OUT"]
            wp = {}
            for t in term:
                res = (_raw(run, item_id, t) or {}).get("result", {})
                cand = res.get("would_post", res)
                if isinstance(cand, dict) and cand:
                    wp = cand
                    break
            items = list(wp.items())
            holds = " · ".join(f'{k} <span class="q">{_html.escape(_short(v))}</span>' for k, v in items) or "the staged result"
            sub = _short(" · ".join(f"{k} {_short(v, 22)}" for k, v in items) or "staged for review", 46)
            n.update(title="staged", w0=250, sub=sub,
                     detail=[["what", "the recipe’s output — staged, never sent automatically"],
                             ["holds", holds],
                             ["next", "a human reviews and posts it, or edits first — nothing is automatic"]])

    # wires → the engine's array form [src, srcSock, dst, dstSock, type?]
    warr = []
    for w in g["wires"]:
        a = [w["src"], w["srcSock"], w["dst"], w["dstSock"]]
        if w["type"] != "data":
            a.append(w["type"])                                 # "gate" | "loop"
        warr.append(a)
    return {"title": title, "desc": desc, "nodes": g["nodes"], "wires": warr}


def _graph_core(template):
    import os
    return open(os.path.join(os.path.dirname(template), "graph_core.js")).read()


def build_html(recipe, run, work_item, title, desc, item_id=None,
               template="engine/explorer_engine.html"):
    data = build_data(recipe, run, work_item, title, desc, item_id)
    html = open(template).read()
    html = (html.replace("__GRAPH_CORE__", _graph_core(template))
                .replace("__NODES__", json.dumps(data["nodes"], ensure_ascii=False))
                .replace("__WIRES__", json.dumps(data["wires"], ensure_ascii=False))
                .replace("__TITLE__", data["title"])
                .replace("__DESC__", data["desc"]))
    return html


if __name__ == "__main__":
    import sys
    from engine.recipes.triage import TRIAGE

    run = load_run(sys.argv[1] if len(sys.argv) > 1 else "state/triage-1783745537.json")
    item = sys.argv[2] if len(sys.argv) > 2 else None
    for c in generate_cards(TRIAGE, run, item):
        print(f"\n### {c['id']}  ({c['specialist']})")
        print(f"  specialty  {c['specialty']}")
        print(f"  tuned      {c['tuned'][:100]}")
        o = c["out"]
        print(f"  → value    {o['value']}")
        if o.get("why"):   print(f"    why      {o['why'][:220]}")
        if o.get("full"):  print(f"    full     {o['full'][:120]}…  ({len(o['full'])} chars, truncate+expand)")
