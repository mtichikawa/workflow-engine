"""respond — DOMAIN specialist (triage): draft a first reply to an issue."""

from __future__ import annotations

from ..core import Contract, Specialist, brain
from ..fewshot import block
from ._util import text_of


class Respond(Specialist):
    name = "respond"
    kind = "domain"
    contract = Contract(input={"item": object, "tone": str}, output={"reply": str})

    def _run(self, input, config):
        prompt = (
            f"Draft a first reply to this ISSUE. Tone: {input['tone']}.\n"
            "Be concise. If information is missing, ask for exactly what's needed "
            "(repro steps, version, logs). Do not promise timelines.\n\n"
            f"ISSUE:\n{text_of(input['item'])}\n\n"
            + (block("respond", input) + "\n\nMatch the voice of those example replies.\n\n"
               if block("respond", input) else "")
            + "Return only the reply text."
        )
        reply = brain(prompt, system="You are a helpful, precise support responder.",
                      temperature=0.3)
        return {"reply": reply.strip()}
