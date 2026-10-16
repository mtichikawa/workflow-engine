"""Care intake → insurance claim: a doula-care case run on SYNTHETIC documents.

A faxed referral, two phone photos of the insurance card, an intake-form PDF, the doula's visit log
and a patient's chat message go in. The workflow reads the scans, fills one record, checks it against
the plan's billing rules, triages the message — anything medical goes to a person, never answered by
the model — and drafts a CMS-1500 claim and a patient reply. It stops at a human gate; approving
stages the packet as a file. Nothing is ever sent.

Reused from the shared library: match, classify, verify, act. Built for this case: read_document,
fill_form and patient_reply (model), coverage_rules, handoff_note, claim_draft, assemble_packet (code).
"""

from __future__ import annotations

from pathlib import Path

from ...core import Edge, Recipe, Step, register
from .documents import DOCUMENTS, PLAN, PRACTICE, SYNTHETIC, payload
from .specialists import (SAFETY_LINE, AssemblePacket, ClaimDraft, CoverageRules, FillForm,
                          HandoffNote, PatientReply, ReadDocument)

TITLE = "Doula care intake → insurance claim"
TAPE = Path(__file__).with_name("tape.json")

REQUEST = ("A new doula client's paperwork just came in: the midwife's faxed referral, photos of the "
           "insurance card, the online intake form, the doula's visit log and a message from the patient. "
           "Read the documents, pull out what the claim needs, check it against the plan's billing rules "
           "and flag anything missing. Triage the patient's message and send anything medical to a person. "
           "Draft the insurance claim and a reply to the patient, and stage it all for approval — send nothing.")

FIELDS = [
    {"name": "patient_first", "type": "text", "required": True},
    {"name": "patient_middle_initial", "type": "text"},
    {"name": "patient_last", "type": "text", "required": True},
    {"name": "date_of_birth", "type": "date", "required": True},
    {"name": "sex", "type": "text", "required": True, "hint": "as listed with the insurance; null if not given"},
    {"name": "member_id", "type": "text", "required": True,
     "hint": "exactly as printed on the insurance card (the intake form is the patient's own typing)"},
    {"name": "plan_name", "type": "text", "required": True},
    {"name": "coverage_effective_date", "type": "date", "required": True},
    {"name": "address", "type": "text", "required": True},
    {"name": "phone", "type": "text"},
    {"name": "preferred_language", "type": "text"},
    {"name": "estimated_due_date", "type": "date"},
    {"name": "recommending_provider", "type": "text", "required": True},
    {"name": "recommending_provider_npi", "type": "text", "required": True},
    {"name": "recommendation_date", "type": "date", "required": True},
    {"name": "recommendation_signed", "type": "yes/no", "required": True,
     "hint": "yes only if a signature appears on the recommendation's signature line; no if it is [blank]"},
    {"name": "services_recommended", "type": "text"},
]

MEDICAL_CRITERIA = (
    "medical if ANY part of the message describes a physical symptom or a change in the body (pain, "
    "bleeding, leaking fluid, swelling, fever, headache, the baby moving less), asks about a medication "
    "or supplement, describes a mental-health concern beyond ordinary nerves (hopelessness, panic that "
    "won't stop, not sleeping for days, not wanting to be here, thoughts of harming herself or the baby), "
    "or asks whether something about the pregnancy, birth, recovery or the baby's health is normal or "
    "safe — even when the rest of the message is about scheduling or coverage. Ordinary worries and "
    "feelings, and logistics (scheduling, coverage, paperwork, what to pack, birth preferences, feeding "
    "routines with no health problem) are non-medical.")

NON_MEDICAL_LINE = (
    "The REPLY holds the non-medical line: it does not describe, assess, explain or reassure about any "
    "symptom or health concern, and suggests no medication, remedy, test or treatment. The only "
    f"health-related text allowed is this approved safety message, word for word: \"{SAFETY_LINE}\" "
    "Any coverage statement agrees with BENEFITS_LEFT, and no specific appointment day is promised.")

RECIPE = Recipe(name="care_intake", max_visits=3, steps=[
    Step(id="read_referral", specialist="read_document", domain=True, inputs={"files": "payload.referral"}),
    Step(id="read_card", specialist="read_document", domain=True, inputs={"files": "payload.card"}),
    Step(id="read_intake", specialist="read_document", domain=True, inputs={"files": "payload.intake"}),
    Step(id="triage", specialist="classify",
         inputs={"item": "payload.message"},
         config={"categories": ["medical", "non-medical"], "criteria": MEDICAL_CRITERIA}),
    Step(id="fields", specialist="fill_form", domain=True,
         inputs={"documents": {"faxed referral": "read_referral.text", "insurance card": "read_card.text",
                               "intake form": "read_intake.text"}},
         config={"fields": FIELDS}),
    Step(id="identity", specialist="match",
         inputs={"a": "read_referral.text", "b": "read_card.text"},
         config={"criteria": "the same person — the referral's patient and the card's member: compare the "
                             "name (ignore order, case, middle initials) and the date of birth (ignore format)"}),
    Step(id="coverage", specialist="coverage_rules", domain=True,
         inputs={"fields": "fields.fields", "identity": "identity", "visits": "payload.visits"},
         config={"plan": PLAN}),
    Step(id="handoff", specialist="handoff_note", domain=True,
         inputs={"triage": "triage", "message": "payload.message", "fields": "fields.fields"}),
    Step(id="claim", specialist="claim_draft", domain=True,
         inputs={"fields": "fields.fields", "coverage": "coverage"},
         config={"billing": {"name": PRACTICE["name"], "address": PRACTICE["address"],
                             "npi": PRACTICE["npi"], "taxonomy": PLAN["taxonomy"]}}),
    Step(id="reply", specialist="patient_reply", domain=True,
         inputs={"message": "payload.message", "medical": "triage.label", "coverage": "coverage",
                 "missing": "fields.missing", "feedback": "reply_check.issues"}),
    Step(id="reply_check", specialist="verify",
         inputs={"subject": {"REPLY": "reply.reply", "BENEFITS_LEFT": "coverage.remaining"}},
         config={"standard": NON_MEDICAL_LINE}),
    Step(id="packet", specialist="assemble_packet", domain=True, gate=True,
         inputs={"claim": "claim", "reply": "reply", "reply_check": "reply_check", "handoff": "handoff",
                 "fields": "fields", "coverage": "coverage"}),
    Step(id="stage", specialist="act",
         inputs={"payload": {"content": "packet.markdown", "name": "case-0042-review-packet.md"}},
         config={"target": "file", "mode": "staged"}),
], edges=[
    Edge("read_referral", "fields"), Edge("read_card", "fields"), Edge("read_intake", "fields"),
    Edge("read_referral", "identity"), Edge("read_card", "identity"),
    Edge("fields", "coverage"), Edge("identity", "coverage"),
    Edge("fields", "handoff"), Edge("triage", "handoff"),
    Edge("coverage", "claim"),
    Edge("coverage", "reply"), Edge("triage", "reply"),
    Edge("reply", "reply_check"),
    Edge("reply_check", "reply", "reply_check.verdict == 'fail'"),    # crossed the line → redraft (≤ 3 drafts)
    Edge("claim", "packet"), Edge("handoff", "packet"), Edge("reply_check", "packet"),
    Edge("packet", "stage"),
])

# What each step does here, for the screen. `how` comes from the specialist itself.
STEPS = {
    "read_referral": "reads the faxed referral (a scan — the model reads the page images)",
    "read_card":     "reads the two card photos",
    "read_intake":   "reads the intake form (a real text layer — no model needed)",
    "triage":        "is anything in the patient's message medical?",
    "fields":        "fills one record from all three documents, citing each source",
    "identity":      "is the referred patient the card's member?",
    "coverage":      "checks the plan's billing rules and counts benefits left",
    "handoff":       "routes medical content to a person",
    "claim":         "fills the CMS-1500 claim draft",
    "reply":         "drafts the patient reply — non-medical only",
    "reply_check":   "checks the reply holds the non-medical line",
    "packet":        "puts the drafts in front of a person",
    "stage":         "writes the approved packet to a file — never sends",
}

# What a person reading the graph sees: each step's name in plain English, and what each column of the graph
# is for (columns are the data-flow depth from engine.explorer.build_graph: 0 = the case file; its OUT column isn't drawn).
LABELS = {
    "read_referral": "Read the fax",
    "read_card":     "Read the card photos",
    "read_intake":   "Read the intake form",
    "triage":        "Medical or not?",
    "fields":        "Fill one record",
    "identity":      "Same person?",
    "coverage":      "Check billing rules",
    "handoff":       "Note for the nurse",
    "claim":         "Draft the claim",
    "reply":         "Draft the reply",
    "reply_check":   "Check the reply",
    "packet":        "A person approves",
    "stage":         "Save for the team",
}
# Steps measured on a sealed blind set (docs/blind-evals.md). The box shows the result, read from the file in
# evals/blind-results/: the step as configured, the same model without its written rules, and `examples` (item
# ids) the rule-less model got wrong.
TESTED = {"triage": {"result": "triage.json", "with": "engine (policy)", "without": "same model, no policy",
                     "examples": ["m239", "m311"]}}

PHASES = ["Comes in", "Read", "Combine", "Rules and routing", "Draft", "Check", "Approve", "Save"]

_SPECIALISTS = (ReadDocument(), FillForm(), CoverageRules(), PatientReply(), HandoffNote(), ClaimDraft(),
                AssemblePacket())


def load() -> None:
    """Register this case's domain specialists (the shared library is registered by engine.specialists)."""
    from ... import specialists  # noqa: F401
    for s in _SPECIALISTS:
        register(s)


__all__ = ["DOCUMENTS", "FIELDS", "RECIPE", "REQUEST", "STEPS", "SYNTHETIC", "TAPE", "TESTED", "TITLE",
           "load", "payload"]
