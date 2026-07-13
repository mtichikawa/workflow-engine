"""write — DOMAIN specialist (content): draft a short post from a topic + sources."""

from __future__ import annotations

from ..core import Contract, Specialist, brain
from ..fewshot import block
from ._util import text_of


class Write(Specialist):
    name = "write"
    kind = "domain"
    contract = Contract(
        input={"topic": object, "sources": object, "brief": str},
        output={"post": str},
    )

    def _run(self, input, config):
        fs = block("write", input)
        # Optional revise-loop input (extra field, not in the contract): if a prior draft was
        # reviewed and flagged, address the feedback instead of drafting from scratch. This is
        # what lets a draft→verify→revise recipe LOOP until it passes.
        feedback = input.get("feedback")
        prior = input.get("prior_post")
        revising = bool(feedback)
        prompt = (
            f"Write a short, punchy social post about this TOPIC.\n"
            f"Brief / voice: {input['brief']}\n"
            "No hype, no emojis. Numbers over adjectives. 2-4 sentences.\n\n"
            f"TOPIC:\n{text_of(input['topic'])}\n\n"
            f"REFERENCE SOURCES (for grounding, don't quote verbatim):\n{text_of(input['sources'])}\n\n"
            + (f"A PRIOR DRAFT was reviewed and flagged these issues — write a NEW draft that "
               f"avoids them:\nISSUES: {text_of(feedback)}\n"
               + (f"PRIOR DRAFT (for reference): {text_of(prior)}\n" if prior else "") + "\n"
               if revising else "")
            + (fs + "\n\nMatch the voice of those example posts.\n\n" if fs else "")
            + "Return only the post text."
        )
        post = brain(prompt, system="You write crisp, credible short-form posts.",
                     temperature=0.4)
        return {"post": post.strip()}
