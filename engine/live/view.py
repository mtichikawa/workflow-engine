"""How a case's workflow looks on screen — one source for the live demo and the public site's replay.

    graph(case)              the explorer's full graph (engine.explorer.build_graph, every connection by
                             name): each box named in plain English, its specialist and method under the name,
                             the case's column names, and what is reused from the library vs written for it
    step_detail(case, ...)   a box's click-to-open rows once its step has run: does / specialist / result /
                             why / see / time
    findings(outputs)        what the run found, one plain-English line each, tied to the step that found it

The live page asks for these as a run unfolds; the site builder bakes them from the recorded run.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from ..core import get
from ..explorer import build_graph
from ..specialists import CAPABILITIES, DOMAIN
from .care_intake.render import FIELD_LABELS

LIBRARY = list(CAPABILITIES) + list(DOMAIN)
RESULTS = Path(__file__).resolve().parents[2] / "evals" / "blind-results"


def sock(name: str) -> str:
    """A connection's name as a reader sees it: verify's template slots (REPLY, BENEFITS_LEFT) in plain words."""
    return name.lower().replace("_", " ")


def summary(spec: str, o: dict) -> str:
    """One line from a step's output — the result row of its box."""
    if spec == "read_document":
        return o["method"].replace("model read", "the model read").replace("text layer (no model)", "read the text layer, no model")
    if "label" in o:
        return f"{o['label']} ({o['confidence']})"
    if "same" in o:
        return f"same person ({o['confidence']})" if o["same"] else "NOT the same person"
    if "missing" in o:
        return f"{len(o['fields'])} fields · {len(o['missing'])} missing" + (f" ({', '.join(o['missing'])})" if o["missing"] else "")
    if "checks" in o:
        bad = [c["problem"] for c in o["checks"] if not c["met"]]
        return f"{len(bad)} rule not met: {bad[0].lower()}" if len(bad) == 1 else f"{len(bad)} rules not met" if bad else "all rules met"
    if "needed" in o:
        return "→ on-call nurse (a person)" if o["needed"] else "no medical content"
    if "holds" in o:
        return f"CMS-1500 {'on hold · ' + str(len(o['holds'])) + ' issues' if o['holds'] else 'clean'}"
    if "safety_line" in o:
        return "coverage + scheduling only" + (" + fixed safety text" if o["safety_line"] else "")
    if "verdict" in o:
        return f"{o['verdict']}: {'holds' if o['verdict'] == 'pass' else 'crosses'} the non-medical line"
    if "documents" in o:
        return "waiting for a person"
    if "status" in o:
        return "writes the file, never sends"
    return "done"


def how(case, st, output: dict | None = None) -> str:
    """How a step does its work, in words. A document reader's answer depends on the file: a scan goes to the
    model, a PDF with a text layer doesn't — from the run's own record when there is one, else from the file."""
    if st.specialist == "read_document":
        if output and "method" in output:
            model = "no model" not in output["method"]
        else:
            from .care_intake.specialists import reads_with_model
            model = reads_with_model(case.payload()[st.inputs["files"].split(".", 1)[1]])
        return "the model reads the images" if model else "plain code (the PDF has text)"
    return getattr(get(st.specialist), "how", None) or ("plain code" if st.specialist in ("act", "fetch") else "the model")


def _kind(method: str) -> str:
    return "code" if method.startswith(("plain code", "code")) else "model"


def _more(label: str, text: str) -> str:
    """A row's click-to-open text: the label shows, the text opens under it."""
    return f'<span class="rmore">{html.escape(label)} ▸</span><div class="rfull">{html.escape(text)}</div>'


def _tested(spec: dict) -> str:
    """A step's blind-set result (case.TESTED), read from its result file: caught and false alarms with the
    step's written rules, then the same model without them, with messages that model wrongly flagged."""
    r = json.loads((RESULTS / spec["result"]).read_text())
    a, b = (r["systems"][spec[k]]["all"] for k in ("with", "without"))
    text = {i["id"]: i["text"] for i in r["items"]}
    assert set(spec["examples"]) <= set(b["false_alarm_ids"]) - set(a["false_alarm_ids"]), spec["examples"]
    count = lambda m: f"{m['k']}/{m['n']}"
    caught, fa = "caught (sensitivity)", "false alarms"
    return (f"on {r['n']} messages written blind: <b>{count(a[caught])}</b> medical ones sent to a person, "
            f"<b>{count(a[fa])}</b> false alarms. The same model without this written policy: {count(b[caught])}, "
            f"but <b>{count(b[fa])}</b> false alarms ({b[fa]['rate']:.0%}), e.g. "
            + " · ".join(f"“{html.escape(text[i])}”" for i in spec["examples"]))


def _rows(case, st, method: str) -> list:
    e = lambda x: html.escape(str(x))
    reused = st.specialist in LIBRARY
    does = case.STEPS[st.id]
    rows = [["does", e(does[0].upper() + does[1:])],
            ["specialist", f"<code>{e(st.specialist)}</code> · {'reused from the library' if reused else 'built for this job'} · {e(method)}"]]
    rules = st.config.get("criteria") or st.config.get("standard")
    if rules:
        rows.append(["rules", _more("show the written rules", rules)])
    if st.id in getattr(case, "TESTED", {}):
        rows.append(["tested", _tested(case.TESTED[st.id])])
    return rows


def step_detail(case, step_id: str, output: dict, seconds: float | None) -> dict:
    """A finished step's box: the line under its name and its click-to-open rows (HTML-escaped)."""
    e = lambda x: html.escape(str(x))
    st = next(s for s in case.RECIPE.steps if s.id == step_id)
    o, method = output or {}, how(case, st, output)
    rows = _rows(case, st, method) + [["result", e(summary(st.specialist, o))]]
    why = o.get("reasoning") or ("; ".join(o["issues"]) if isinstance(o.get("issues"), list) and o["issues"] else "")
    if why:
        rows.append(["why", e(why)])
    full = {"read_document": ("show what it read", o.get("text")), "patient_reply": ("show the reply", o.get("reply")),
            "handoff_note": ("show the note", o.get("note")),
            "claim_draft": ("show the holds", "\n".join(o.get("holds", []))),
            "coverage_rules": ("show the checks", "\n".join(f"{'✓' if c['met'] else '✗'} {c['check']}" for c in o.get("checks", [])))
            }.get(st.specialist)
    if full and full[1]:
        rows.append(["see", _more(*full)])
    rows.append(["time", f"{seconds:.1f} s" if seconds and seconds > 0.1 else "instant"])
    return {"sub": f"{st.specialist} · {_kind(method)}", "detail": rows}


def graph(case, results: dict | None = None) -> dict:
    """The case's graph. With `results` ({step_id: {"output", "seconds"}}, a recorded run) every box carries
    its full detail; without, each box has its static rows and the page fills the rest as steps finish."""
    g = build_graph(case.RECIPE, work_item="case")
    by_id = {st.id: st for st in case.RECIPE.steps}
    nodes = []
    for n in g["nodes"]:
        n = {**n, "outs": [sock(o) for o in n["outs"]], "ins": [i if i.startswith("when ") else sock(i) for i in n["ins"]]}
        if n["id"] == "IN":
            docs = [d["title"] for d in case.DOCUMENTS if d["id"] != "plan"]
            nodes.append({**n, "kind": "in", "title": "The case file", "sub": f"{len(n['outs'])} documents, as received",
                          "detail": [["what", "everything that came in for this client"],
                                     ["holds", html.escape(" · ".join(docs))]]})
            continue
        if n["id"] == "OUT":
            continue                                   # "Save for the team" is the end; a separate OUT box repeats it
        st = by_id[n["id"]]
        kind = "gate" if st.gate else ("shared" if st.specialist in LIBRARY else "domain")
        r = (results or {}).get(st.id)
        if r:
            box = step_detail(case, st.id, r["output"], r.get("seconds"))
        else:
            method = how(case, st)
            box = {"sub": f"{st.specialist} · {_kind(method)}", "detail": _rows(case, st, method)}
        nodes.append({**n, "kind": kind, "title": case.LABELS[st.id], **box})
    wires = []
    for w in g["wires"]:
        if w["dst"] == "OUT":
            continue
        a = [w["src"], sock(w["srcSock"]), w["dst"], w["dstSock"] if w["dstSock"].startswith("when ") else sock(w["dstSock"])]
        if w["type"] != "data":
            a.append(w["type"])
        wires.append(a)
    ncols = max(n["col"] for n in nodes) + 1
    assert len(case.PHASES) == ncols, f"{case.__name__}.PHASES names {len(case.PHASES)} columns; the graph has {ncols}"
    used = {st.specialist for st in case.RECIPE.steps}
    lib = used & set(LIBRARY)
    return {"nodes": nodes, "wires": wires, "phases": case.PHASES,
            "lib": sorted(lib), "own": sorted(used - lib), "lib_size": len(LIBRARY)}


def _field(name: str) -> str:
    """A form field's name mid-sentence: "Member ID" -> "member ID", "Sex (as on insurance)" -> "sex"."""
    label = FIELD_LABELS.get(name, name.replace("_", " ")).split(" (")[0]
    return label if label[1:2].isupper() else label[0].lower() + label[1:]


def findings(out: dict) -> list[dict]:
    """What the run found, in plain English — one line each, tied to the step that found it. `out` maps step
    ids to outputs; steps that haven't finished yet are left out. tone: "warn" needs a person, "ok" is fine."""
    f = []
    if "triage" in out and out["triage"]["label"] == "medical":
        f.append({"step": "triage", "tone": "warn", "text": "The patient's message is medical, so it goes to the on-call nurse. "
                                                             "The reply to the patient doesn't answer it."})
    if "identity" in out:
        f.append({"step": "identity", "tone": "ok", "text": "The referral and the insurance card are for the same person."}
                 if out["identity"]["same"] else
                 {"step": "identity", "tone": "warn", "text": "The referral and the insurance card may be different people."})
    for c in out.get("coverage", {}).get("checks", []):
        if not c["met"]:
            f.append({"step": "coverage", "tone": "warn", "text": f"{c['problem']}: {c['detail']}."})
    fields = out.get("fields", {}).get("fields", {})
    for m in out.get("fields", {}).get("missing", []):
        name, seen = _field(m), (fields.get(m) or {}).get("unreadable")
        f.append({"step": "fields", "tone": "warn", "text":
                  f"Part of the {name} on the {fields[m]['source']} can't be read ({seen}), so a person checks it."
                  if seen else f"The claim needs the patient's {name}, and no document gives it."})
    if "claim" in out:
        holds = out["claim"]["holds"]
        f.append({"step": "claim", "tone": "warn" if holds else "ok",
                  "text": f"So the claim is on hold, with {len(holds)} issue{'s' if len(holds) != 1 else ''} to fix first." if holds
                  else "The claim is complete."})
    if "reply_check" in out:
        ok = out["reply_check"]["verdict"] == "pass"
        f.append({"step": "reply_check", "tone": "ok" if ok else "warn",
                  "text": "The reply sticks to coverage and scheduling, and passed its check." if ok
                  else "The reply failed its check and went back to be redrafted."})
    return f
