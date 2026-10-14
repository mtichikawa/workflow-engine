"""route — DOMAIN specialist (triage): send an issue to the right component / escalate."""

from __future__ import annotations

from ..core import Contract, Specialist, brain_json
from ..fewshot import block
from ._util import one_sentence, text_of


class Route(Specialist):
    name = "route"
    kind = "domain"
    description = (
        "[domain] Route an issue/request to exactly one component and decide escalation. "
        "USE WHEN triaging to owners WITH an escalate decision. "
        "NOT general categorization without ownership/escalation (->classify). "
        "CONFIG components list; TAILORED to your routing convention via examples. "
        "IN item,components -> OUT component,escalate,reasoning."
    )
    contract = Contract(
        input={"item": object, "components": list},
        output={"component": str, "escalate": bool, "reasoning": str},
    )

    def output_values(self, field, config):
        return list(config["components"]) if field == "component" and isinstance(config.get("components"), list) else None

    def _run(self, input, config):
        components = input["components"]
        fs = block("route", input)
        prompt = (
            f"Route this ISSUE to exactly one component from: {components}\n"
            "Also decide whether it should be escalated (security, data-loss, outage).\n\n"
            f"ISSUE:\n{text_of(input['item'])}\n\n"
            + (fs + "\n\n" if fs else "")
            + 'Return JSON: {"component": <one component>, "escalate": <true|false>, '
              '"reasoning": <one short sentence>}'
        )
        r = brain_json(prompt, system="You are a support-routing specialist.", temperature=0.0)
        comp = str(r.get("component", "")).strip()
        if comp not in components:
            comp = next((c for c in components if c.lower() in comp.lower()), components[-1])
        return {"component": comp, "escalate": bool(r.get("escalate", False)),
                "reasoning": one_sentence(r.get("reasoning"))}
