"""The review packet: the drafts a person reads at the gate, as documents rather than JSON.

A document is {id, title, audience, blocks}; a block is one of
    {"kv": [[label, value], ...]}  {"table": {"head": [...], "rows": [[...], ...]}}
    {"p": text}  {"pre": text}  {"list": [...], "label"?: text}  {"note": text, "tone": "ok"|"warn"|"info"}
The live page renders blocks to HTML; to_markdown() writes the same packet as the staged file.
"""

from __future__ import annotations

FIELD_LABELS = {
    "patient_first": "First name", "patient_middle_initial": "Middle initial", "patient_last": "Last name",
    "date_of_birth": "Date of birth", "sex": "Sex (as on insurance)", "member_id": "Member ID",
    "plan_name": "Plan", "coverage_effective_date": "Coverage effective", "address": "Address",
    "phone": "Phone", "preferred_language": "Language", "estimated_due_date": "Due date",
    "recommending_provider": "Recommending provider", "recommending_provider_npi": "Provider NPI",
    "recommendation_date": "Recommendation date", "recommendation_signed": "Recommendation signed",
    "services_recommended": "Services recommended",
}


def packet(inp: dict) -> list[dict]:
    claim, reply, check = inp["claim"], inp["reply"], inp["reply_check"]
    handoff, fields, cov = inp["handoff"], inp["fields"], inp["coverage"]

    claim_doc = {"id": "claim", "title": "Insurance claim (CMS-1500)", "audience": "Billing — a person submits it",
                 "blocks": [
        {"note": claim["status"], "tone": "warn" if claim["holds"] else "ok"},
        {"table": {"head": ["Box", "Field", "Value"],
                   "rows": [[b["box"], b["label"], b["value"] or "— EMPTY"] for b in claim["boxes"]]}},
        {"table": {"head": ["24A date", "24B POS", "24D code", "24E", "24F charges", "24G units", "24J NPI", "Service"],
                   "rows": [[l["24A"], l["24B"], l["24D"], l["24E"], l["24F"], l["24G"], l["24J"], l["what"]]
                            for l in claim["lines"]]}},
    ] + ([{"list": claim["holds"], "label": "Holding the claim"}] if claim["holds"] else [])}

    reply_doc = {"id": "reply", "title": "Reply to the patient", "audience": "The patient, in the app — sent only after approval",
                 "blocks": [
        {"p": reply["reply"]},
        {"note": ("Checked against the non-medical line: " + check["verdict"].upper()
                  + (" — " + "; ".join(check["issues"]) if check["issues"] else "")),
         "tone": "ok" if check["verdict"] == "pass" else "warn"},
    ] + ([{"note": "The safety paragraph is fixed text inserted by code — the model did not write it.",
           "tone": "info"}] if reply.get("safety_line") else [])}

    handoff_doc = {"id": "handoff", "title": "Clinical handoff", "audience": handoff["to"] or "Not needed",
                   "blocks": ([{"note": "Medical content found — routed to a person. The assistant did not answer it.",
                                "tone": "warn"}, {"pre": handoff["note"]}]
                              if handoff["needed"] else [{"note": handoff["note"], "tone": "ok"}])}

    missing = [FIELD_LABELS.get(m, m) for m in fields.get("missing", [])]
    unmet = [f"{c['problem']} — {c['detail']}" for c in cov["checks"] if not c["met"]]
    open_doc = {"id": "open", "title": "Open items", "audience": "Care coordinator",
                "blocks": ([{"list": unmet, "label": "Plan rules not met"}] if unmet else [])
                + ([{"list": missing, "label": "Missing from every document"}] if missing else [])
                + [{"table": {"head": ["Benefit", "Left this pregnancy"],
                              "rows": [[r["benefit"], r["left"]] for r in cov["remaining"]]}}]}

    record_doc = {"id": "record", "title": "Case record", "audience": "What was read, and from which document",
                  "blocks": [{"table": {"head": ["Field", "Value", "From"],
                                        "rows": [[FIELD_LABELS.get(k, k), _show(v["value"]), v["source"] or "—"]
                                                 for k, v in fields["fields"].items()]}}]}
    return [claim_doc, reply_doc, handoff_doc, open_doc, record_doc]


def _show(v) -> str:
    return "— (not in any document)" if v is None else str(v)


def to_markdown(docs: list[dict]) -> str:
    out = ["# Review packet — SYNTHETIC case (demo data, nothing real)", ""]
    for d in docs:
        out += [f"## {d['title']}", f"_{d['audience']}_", ""]
        for b in d["blocks"]:
            if "kv" in b:
                out += [f"- **{k}:** {v}" for k, v in b["kv"]] + [""]
            elif "table" in b:
                t = b["table"]
                out += ["| " + " | ".join(t["head"]) + " |", "|" + "---|" * len(t["head"])]
                out += ["| " + " | ".join(str(x) for x in r) + " |" for r in t["rows"]] + [""]
            elif "list" in b:
                out += ([f"**{b['label']}:**"] if b.get("label") else []) + [f"- {x}" for x in b["list"]] + [""]
            elif "pre" in b:
                out += ["```", b["pre"], "```", ""]
            elif "p" in b:
                out += [b["p"], ""]
            elif "note" in b:
                out += [f"> {b['note']}", ""]
    return "\n".join(out)
