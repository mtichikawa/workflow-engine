"""Phase 21 — the final mechanism test: a TAILORED voice layer on top of the BASELINE,
through the scope seam. Does a tenant's small tailored set actually WIN in retrieval and
shift RESPOND's voice, sitting alongside the larger baseline set?

The test voice is deliberately UNLIKE the baseline "sharp, warm maintainer" — a formal
corporate enterprise-support register — so pass/fail is unmistakable. We run RESPOND on a
FRESH issue under baseline vs. under the tenant scope, and we INSTRUMENT retrieval: how many
of the injected few-shot examples came from the tenant layer vs. baseline. If baseline
out-populates the slots, the voice won't shift and we need to weight tailored above baseline.

    python examples/tailored_voice_demo.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import fewshot, scope, specialists  # noqa: F401
from engine.core import get
from engine.examples import path, save_example

TENANT = "acme_corp"
TONE = "our company support voice"

# A tenant's tailored golds — deliberately formal/corporate, nothing like the maintainer baseline.
TENANT_GOLDS = [
    ({"item": {"title": "Export button does nothing",
               "body": "I click export and no file downloads."}, "tone": TONE},
     {"reply": "Dear Valued Customer,\n\nThank you for contacting Acme Support. We sincerely "
      "apologize for the inconvenience you have experienced with the export function. To assist "
      "you further, kindly provide your account ID and the browser you are using. A member of our "
      "team will review your case and follow up within one business day.\n\nWarm regards,\nAcme "
      "Support Team"}),
    ({"item": {"title": "Login fails intermittently",
               "body": "Sometimes I can't log in."}, "tone": TONE},
     {"reply": "Dear Valued Customer,\n\nThank you for reaching out to Acme Support regarding your "
      "login difficulties. We understand how important reliable access is to your work. Could you "
      "please confirm the approximate times the issue occurs and your account email? Our team will "
      "investigate promptly and update you accordingly.\n\nWarm regards,\nAcme Support Team"}),
    ({"item": {"title": "Report shows wrong totals",
               "body": "The monthly report numbers look off."}, "tone": TONE},
     {"reply": "Dear Valued Customer,\n\nThank you for bringing this to our attention, and please "
      "accept our apologies for any confusion. So that we may investigate the discrepancy in your "
      "monthly report, kindly share the reporting period in question and a screenshot if "
      "available. We value your business and will resolve this matter with the utmost priority."
      "\n\nWarm regards,\nAcme Support Team"}),
    ({"item": {"title": "How do I add a teammate?",
               "body": "Need to invite a colleague."}, "tone": TONE},
     {"reply": "Dear Valued Customer,\n\nThank you for your inquiry. We are delighted to assist you "
      "in adding a teammate. Please navigate to Settings and select Team Members, where you may "
      "extend an invitation. Should you require further guidance, our team remains at your "
      "service.\n\nWarm regards,\nAcme Support Team"}),
    ({"item": {"title": "Billing charged me twice",
               "body": "I see two charges this month."}, "tone": TONE},
     {"reply": "Dear Valued Customer,\n\nThank you for notifying us, and we sincerely apologize for "
      "the billing discrepancy. Your satisfaction is our priority. Kindly provide the invoice "
      "numbers for both charges, and our billing department will review your account and issue any "
      "appropriate resolution without delay.\n\nWarm regards,\nAcme Support Team"}),
    ({"item": {"title": "App is slow today",
               "body": "Everything loads slowly."}, "tone": TONE},
     {"reply": "Dear Valued Customer,\n\nThank you for your patience and for informing us of the "
      "performance concerns you are experiencing. We take such matters seriously. To help us "
      "diagnose the issue, could you kindly advise your region and the approximate time the "
      "slowdown began? A member of our team will follow up shortly.\n\nWarm regards,\nAcme Support "
      "Team"}),
    ({"item": {"title": "Can I get a refund?",
               "body": "Not happy with the plan."}, "tone": TONE},
     {"reply": "Dear Valued Customer,\n\nThank you for reaching out, and we regret to learn that the "
      "plan has not met your expectations. We would be glad to review your eligibility for a "
      "refund. Kindly confirm your account email and the plan in question, and our team will "
      "process your request in accordance with our policy.\n\nWarm regards,\nAcme Support Team"}),
]

FRESH = {"title": "The dashboard won't load after the latest update",
         "body": "Since updating this morning, the dashboard is stuck on a blank screen."}


def _keyset(golds):
    return {json.dumps(g, sort_keys=True, default=str) for g in golds}


def _seed_tenant():
    p = path("respond", TENANT)
    if p.exists():
        p.unlink()
    for inp, out in TENANT_GOLDS:
        save_example("respond", inp, out, scope_name=TENANT)


def _run_and_report(label):
    inp = {"item": FRESH, "tone": TONE}
    retrieved = fewshot.retrieve("respond", inp, k=6)
    tenant_keys = _keyset([{"input": i, "output": o} for i, o in TENANT_GOLDS])
    n_tenant = sum(1 for r in retrieved if json.dumps(r, sort_keys=True, default=str) in tenant_keys)
    reply = get("respond").run(inp, {})["reply"]
    print(f"\n===== {label} =====")
    print(f"few-shot slots: {len(retrieved)} injected — {n_tenant} tenant / {len(retrieved) - n_tenant} baseline")
    print("reply:\n" + reply)
    return reply, n_tenant


def main():
    _seed_tenant()
    print(f"seeded {len(TENANT_GOLDS)} tenant golds -> state/examples/{TENANT}/respond.jsonl (formal voice)")
    print(f"baseline respond golds: {len(fewshot.load('respond'))} (baseline scope)")

    base_reply, _ = _run_and_report("BASELINE (no tenant scope)")
    with scope.use_scope(TENANT):
        tail_reply, n_tenant = _run_and_report(f"TAILORED (--scope {TENANT})")

    print("\n===== VERDICT =====")
    formal = tail_reply.strip().startswith("Dear") and "Acme Support" in tail_reply
    print(f"tenant examples reached the few-shot slots: {n_tenant}/6")
    print(f"tailored reply took the formal Acme voice: {formal}")
    if formal and n_tenant >= 1:
        print("PASS — the tailored layer won retrieval and shifted the voice, through the scope seam.")
    else:
        print("NEEDS WEIGHTING — baseline out-populated the slots; rank the tenant layer above baseline.")


if __name__ == "__main__":
    main()
