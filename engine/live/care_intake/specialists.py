"""Domain specialists for the care-intake case.

Three call the model: reading scanned pages, filling the record, writing the patient reply. The rest
are plain code on purpose: plan rules, the CMS-1500 claim, the clinical handoff and the review packet
are the parts a healthcare team wants deterministic and auditable — rules and templates, not judgment.
Each declares which it is (`how`), and the live view labels it.

The reused library capabilities (match, classify, verify, act) are the shared instances — nothing is
cloned here.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from pathlib import Path

from ...core import Contract, Specialist, brain, brain_json
from ...specialists._util import one_sentence, text_of
from .render import packet, to_markdown

PAGES_DIR = Path("state/live/pages")      # page images cut out of scanned PDFs (runtime state, not source)

# Written and approved by people, never by the model. Inserted by code whenever the message was flagged
# medical, so the urgent-care line can't be paraphrased, softened or dropped.
SAFETY_LINE = ("I can't advise on symptoms, so I've passed your message to your care team and a nurse "
               "will reach out to you. If anything feels severe or urgent, call 911 or go to labor and "
               "delivery now.")
SIGN_OFF = "— Your doula care team"


def _values(fields: dict) -> dict:
    return {k: (v or {}).get("value") for k, v in fields.items()}


def _iso(d: str | None) -> str | None:
    if not d:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(d, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


UNREADABLE = "[?]"


def _norm(value, typ: str):
    """Coerce a model-read value to the field's type; anything unreadable is None (= missing). A value with
    a character the reader couldn't make out ([?]) is None too: a gap a person fills, never a guess."""
    if value in (None, "", "null", "None", "unknown", "n/a", "N/A", "blank", "[blank]") or UNREADABLE in str(value):
        return None
    s = str(value).strip()
    if typ == "int":
        m = re.search(r"\d+", s)
        return int(m.group()) if m else None
    if typ == "yes/no":
        low = s.lower()
        return "yes" if low.startswith(("y", "true")) else "no" if low.startswith(("n", "false")) else None
    if typ == "date":
        return _iso(s) or s
    return s


class ReadDocument(Specialist):
    name = "read_document"
    kind = "domain"
    how = "code + model for scans"
    description = (
        "[domain] Turn an incoming document into text: a PDF's text layer is read directly; a scan, fax "
        "or photo is transcribed by the model from its page images, blanks and checkboxes kept as seen. "
        "USE WHEN documents arrive as PDFs/images. IN files -> OUT text,method,pages."
    )
    contract = Contract(input={"files": list}, output={"text": str, "method": str, "pages": int})

    def _run(self, input, config):
        texts, images = [], []
        for f in input["files"]:
            if f.lower().endswith(".pdf"):
                import pypdf
                reader = pypdf.PdfReader(f)
                layer = "\n".join(p.extract_text() or "" for p in reader.pages).strip()
                if len(layer) > 40:                                    # a real text layer: no model needed
                    texts.append(layer)
                    continue
                PAGES_DIR.mkdir(parents=True, exist_ok=True)
                for n, page in enumerate(reader.pages, 1):             # image-only (a fax): cut out the pages
                    out = PAGES_DIR / f"{Path(f).stem}-p{n}.png"
                    page.images[0].image.convert("L").save(out)
                    images.append(str(out))
            else:
                images.append(f)
        if not images:
            return {"text": "\n\n".join(texts), "method": "text layer (no model)", "pages": len(texts)}
        r = brain(
            f"Transcribe the {len(images)} attached page image(s) — a scanned fax, form or photo of a card. "
            "Copy every printed and handwritten line exactly as it appears, in reading order, one page after "
            "another (mark each '--- page N ---'). Keep labels with their values. Write [blank] for an empty "
            "field or signature line, [X] for a checked box and [ ] for an empty one. Where you cannot make out "
            "a character with confidence — blur, glare, a fold — write [?] in its place instead of your best "
            "guess; IDs, numbers and dates especially. Do not correct, complete or summarize anything. Output "
            "only the transcription.",
            system="You are a meticulous document transcriber.", files=images)
        return {"text": "\n\n".join(texts + [r.strip()]), "method": f"model read {len(images)} page image(s)",
                "pages": len(images) + len(texts)}


class FillForm(Specialist):
    name = "fill_form"
    kind = "domain"
    how = "model"
    description = (
        "[domain] Fill a named, typed set of fields from a bundle of source documents, citing which "
        "document each value came from; a field that isn't stated is left empty, never guessed. "
        "USE WHEN turning forms/letters/cards into one structured record (claims, intake, onboarding). "
        "NOT a list of things mentioned (->extract), one label (->classify). "
        "CONFIG fields [{name,type,required,hint}]. IN documents,fields -> OUT fields,missing,reasoning."
    )
    contract = Contract(input={"documents": dict, "fields": list},
                        output={"fields": dict, "missing": list, "reasoning": str})

    def _run(self, input, config):
        spec = input["fields"]
        wanted = "\n".join(f"- {f['name']} ({f['type']})" + (f": {f['hint']}" if f.get("hint") else "")
                           for f in spec)
        docs = "\n\n".join(f"=== {name} ===\n{text}" for name, text in input["documents"].items())
        r = brain_json(
            "Fill each FIELD from the DOCUMENTS. Copy what they state; do not infer, calculate or guess. "
            "A field that is not stated — or is [blank] / 'No answer' on a form — is null. Keep any [?] (a "
            "character the reader couldn't make out) exactly where it is in the value.\n"
            "Dates as YYYY-MM-DD. yes/no fields as \"yes\" or \"no\".\n\n"
            f"FIELDS:\n{wanted}\n\nDOCUMENTS:\n{docs}\n\n"
            'Return JSON: {"fields": {<name>: {"value": <value or null>, "source": <document name or null>}}, '
            '"reasoning": <one short sentence>}',
            system="You are a careful medical-records clerk. You transcribe; you never fill gaps.")
        got = r.get("fields") or {}
        fields = {}
        for f in spec:
            cell = got.get(f["name"])
            cell = cell if isinstance(cell, dict) else {"value": cell, "source": None}
            v = _norm(cell.get("value"), f["type"])
            fields[f["name"]] = {"value": v, "source": cell.get("source") if v is not None else None}
            if v is None and UNREADABLE in str(cell.get("value")):
                fields[f["name"]].update(unreadable=str(cell["value"]), source=cell.get("source"))
        missing = [f["name"] for f in spec if f.get("required") and fields[f["name"]]["value"] is None]
        return {"fields": fields, "missing": missing, "reasoning": one_sentence(r.get("reasoning"))}


def parse_visits(csv_text: str, plan: dict) -> list[dict]:
    """The doula app's visit export -> billable service lines (code, POS, minutes) per the plan's codes."""
    kinds = {"initial visit": "Z1032", "prenatal visit": "Z1034", "postpartum visit": "Z1038",
             "postpartum extended visit": "T1032", "labor and delivery": "59409"}
    pos = {"home": "12", "office": "11", "telehealth": "02", "hospital": "21"}
    codes = {c["code"]: c for c in plan["codes"]}
    lines = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        code = kinds.get(row["visit_type"].strip().lower())
        start, end = (datetime.strptime(row[k], "%H:%M") for k in ("start", "end"))
        lines.append({"visit": row["visit_id"], "date": row["date"], "kind": row["visit_type"],
                      "code": code, "modifier": plan["modifier"],
                      "pos": pos.get(row["location_type"].strip().lower(), "99"),
                      "dx": codes[code]["dx"][0] if code in codes else None,
                      "minutes": int((end - start).total_seconds() // 60), "units": 1,
                      "rendering": row["doula"], "rendering_npi": row["doula_npi"]})
    return lines


class CoverageRules(Specialist):
    name = "coverage_rules"
    kind = "domain"
    how = "code — fixed rules"
    description = (
        "[domain] Check a case against a health plan's doula billing rules — the recommendation, "
        "eligibility, dates and frequency limits — and count the benefits left. Fixed rules in code, "
        "not model judgment. IN fields,identity,visits,plan -> OUT lines,checks,payable,remaining."
    )
    contract = Contract(input={"fields": dict, "identity": dict, "visits": str, "plan": dict},
                        output={"lines": list, "checks": list, "payable": bool, "remaining": list})

    def _run(self, input, config):
        f, plan = _values(input["fields"]), input["plan"]
        lines = parse_visits(input["visits"], plan)
        npi = str(f.get("recommending_provider_npi") or "")
        rec_date, eff = _iso(f.get("recommendation_date")), _iso(f.get("coverage_effective_date"))
        first_dos = min((l["date"] for l in lines), default=None)
        initial = sum(1 for l in lines if l["code"] == "Z1032")
        perinatal = sum(1 for l in lines if l["code"] in ("Z1034", "Z1038"))
        ident = input["identity"]
        checks = [  # (rule, met, detail, what's wrong when it isn't met)
            ("Recommendation from a licensed provider, with NPI",
             bool(f.get("recommending_provider")) and bool(re.fullmatch(r"\d{10}", npi)),
             f"{f.get('recommending_provider') or 'no provider'} · NPI {npi or 'missing'}",
             "No valid recommending provider and NPI"),
            ("Recommendation signed", f.get("recommendation_signed") == "yes",
             "signed" if f.get("recommendation_signed") == "yes" else "the signature line on the faxed form is blank",
             "Recommendation not signed"),
            ("Member eligible on the date of service", bool(eff and first_dos and eff <= first_dos),
             f"coverage effective {eff or '—'} · service {first_dos or '—'}",
             "Member not shown as eligible on the date of service"),
            ("Service on or after the recommendation date", bool(rec_date and first_dos and rec_date <= first_dos),
             f"recommended {rec_date or '—'} · service {first_dos or '—'}",
             "Service before the recommendation date"),
            ("One initial visit per pregnancy", initial <= 1, f"{initial} billed",
             "More than one initial visit billed"),
            ("Referral and card are the same person", bool(ident.get("same")),
             ident.get("reasoning") or "", "Referral and card may be different people"),
        ]
        checks = [{"check": c, "met": m, "detail": d, "problem": pr} for c, m, d, pr in checks]
        remaining = [
            {"benefit": "Prenatal and postpartum visits (Z1034/Z1038)",
             "left": f"{plan['perinatal_cap'] - perinatal} of {plan['perinatal_cap']}"},
            {"benefit": "Labor and delivery support", "left": "1 of 1"},
            {"benefit": "Extended postpartum visits (T1032)", "left": "2 visits, up to 24 units"},
        ]
        return {"lines": lines, "checks": checks, "payable": all(c["met"] for c in checks),
                "remaining": remaining}


class PatientReply(Specialist):
    name = "patient_reply"
    kind = "domain"
    how = "model + fixed safety text"
    description = (
        "[domain] Draft a short, warm reply to a patient that answers ONLY the non-medical parts "
        "(coverage, scheduling) from given facts; medical content is never answered — a fixed, "
        "human-approved safety line is inserted by code instead. USE WHEN replying to patients. "
        "NOT a reply to a support ticket (->respond). IN message,medical,coverage,missing -> OUT reply,safety_line."
    )
    contract = Contract(input={"message": str, "medical": str, "coverage": dict},
                        output={"reply": str, "safety_line": bool})

    def _run(self, input, config):
        medical = input["medical"] == "medical"
        cov = input["coverage"]
        facts = [f"{r['benefit']}: {r['left']} left" for r in cov.get("remaining", [])]
        holds = [f"{c['problem']} — {c['detail']}" for c in cov.get("checks", []) if not c["met"]]
        asks = [m.replace("_", " ") for m in (input.get("missing") or [])]
        feedback = input.get("feedback")
        prompt = (
            "Write a short reply (under 90 words, no lists) from the patient's doula team to this MESSAGE.\n"
            "Every word you write is sent to the patient: no notes, headers or asides for staff.\n"
            "Plain, warm language at a 6th-grade reading level. Answer only coverage and scheduling, using "
            "ONLY the FACTS. Scheduling: say the care coordinator will call to set a time; don't promise a day.\n"
            + ("The message ALSO contains a medical question or symptom. Do NOT mention, describe, assess or "
               "reassure about it in any way and give no medical advice — the team adds a fixed safety "
               "message about it separately.\n" if medical else "")
            + f"\nMESSAGE:\n{input['message']}\n\nFACTS (benefits left this pregnancy):\n- " + "\n- ".join(facts)
            + ("\nOUR SIDE, STILL OPEN (say we're handling it with her midwife; no jargon):\n- " + "\n- ".join(holds)
               if holds else "")
            + ("\nASK THE PATIENT FOR (one short line):\n- " + "\n- ".join(asks) if asks else "")
            + (f"\n\nA reviewer rejected the previous draft for: {text_of(feedback)}\nFix that." if feedback else "")
            + "\n\nReturn only the body: no greeting with a placeholder name, and no sign-off."
        )
        reply = brain(prompt, system="You write clear, kind messages for a doula care team. "
                                     "You never give medical advice.").strip()
        if medical:
            reply = f"{reply}\n\n{SAFETY_LINE}"
        return {"reply": f"{reply}\n\n{SIGN_OFF}", "safety_line": medical}


class HandoffNote(Specialist):
    name = "handoff_note"
    kind = "domain"
    how = "code — fixed template"
    description = (
        "[domain] When a patient message is medical, write the handoff to a human clinician: who, how to "
        "reach them, the message verbatim, and why it was flagged — a fixed template, no model. "
        "IN triage,message,fields -> OUT needed,to,note."
    )
    contract = Contract(input={"triage": dict, "message": str, "fields": dict},
                        output={"needed": bool, "to": str, "note": str})

    def _run(self, input, config):
        t = input["triage"]
        if t.get("label") != "medical":
            return {"needed": False, "to": "", "note": "No medical content — no clinical handoff."}
        f = _values(input["fields"])
        name = " ".join(x for x in (f.get("patient_first"), f.get("patient_last")) if x) or "unknown"
        note = (f"Patient: {name}  ·  phone {f.get('phone') or 'not on file'}  ·  "
                f"language: {f.get('preferred_language') or 'not stated'}\n"
                f"Due date: {f.get('estimated_due_date') or 'unknown'}  ·  midwife: "
                f"{f.get('recommending_provider') or 'unknown'}\n\n"
                f"Their message, verbatim:\n{input['message']}\n\n"
                f"Why it was flagged: {t.get('reasoning') or 'classified as medical'}\n\n"
                "The assistant did not answer the medical part. It told the patient a nurse will reach out, "
                "and to call 911 or go to labor and delivery if anything feels severe or urgent.")
        return {"needed": True, "to": "Care team — on-call nurse (a person)", "note": note}


class ClaimDraft(Specialist):
    name = "claim_draft"
    kind = "domain"
    how = "code — fixed template"
    description = (
        "[domain] Fill a CMS-1500 claim draft from the record and the coverage result — a fixed "
        "template, no model — and list what keeps it from being a clean claim. "
        "IN fields,coverage,billing -> OUT boxes,lines,status,holds."
    )
    contract = Contract(input={"fields": dict, "coverage": dict, "billing": dict},
                        output={"boxes": list, "lines": list, "status": str, "holds": list})

    def _run(self, input, config):
        f, cov, b = _values(input["fields"]), input["coverage"], input["billing"]
        last, first, mi = f.get("patient_last"), f.get("patient_first"), f.get("patient_middle_initial")
        name = f"{last.upper()}, {first.upper()}{' ' + mi.upper() if mi else ''}" if last and first else None
        dob = f.get("date_of_birth")
        boxes = [
            ("1a", "Insured's ID number", f.get("member_id")),
            ("2", "Patient's name", name),
            ("3", "Patient's birth date", dob),
            ("3", "Sex", f.get("sex")),
            ("5", "Patient's address", f.get("address")),
            ("17", "Referring provider (DN)", f.get("recommending_provider")),
            ("17b", "Referring provider NPI", f.get("recommending_provider_npi")),
            ("21", "Diagnosis (ICD-10), A", cov["lines"][0]["dx"] if cov["lines"] else None),
            ("31", "Signature of physician or supplier", "wet signature at submission (paper)"),
            ("32", "Service facility location", f.get("address") and "Patient's home (POS 12)"),
            ("33", "Billing provider", f"{b['name']} · {b['address']}"),
            ("33a", "Billing NPI", b["npi"]),
            ("33b", "Billing taxonomy", b["taxonomy"]),
        ]
        boxes = [{"box": n, "label": l, "value": v} for n, l, v in boxes]
        lines = [{"24A": l["date"], "24B": l["pos"], "24D": f"{l['code']} {l['modifier']}", "24E": "A",
                  "24F": "per fee schedule", "24G": l["units"], "24J": l["rendering_npi"],
                  "what": f"{l['kind']} · {l['minutes']} min"} for l in cov["lines"]]
        holds = [f"Box {x['box']} ({x['label']}) is empty" for x in boxes if not x["value"]]
        holds += [f"{c['problem']} — {c['detail']}" for c in cov["checks"] if not c["met"]]
        status = ("Draft — on hold, not a clean claim yet" if holds
                  else "Draft — clean, ready for a person to submit")
        return {"boxes": boxes, "lines": lines, "status": status, "holds": holds}


class AssemblePacket(Specialist):
    name = "assemble_packet"
    kind = "domain"
    how = "code — human gate"
    description = (
        "[domain] Put a case's drafts into one review packet for the human gate: the claim, the patient "
        "reply, any clinical handoff and the open items. Fixed layout, no model. "
        "IN claim,reply,reply_check,handoff,fields,coverage -> OUT documents,markdown."
    )
    contract = Contract(input={"claim": dict, "reply": dict, "reply_check": dict, "handoff": dict,
                               "fields": dict, "coverage": dict},
                        output={"documents": list, "markdown": str})

    def _run(self, input, config):
        docs = packet(input)
        return {"documents": docs, "markdown": to_markdown(docs)}
