"""classify — capability specialist: assign an item to one of N categories.

Config-driven (categories + criteria), so the SAME instance classifies issue types
for triage and content angles for content. Low temperature for consistency.
"""

from __future__ import annotations

from ..core import Contract, Specialist, brain_json
from ..fewshot import block
from ._util import num, one_sentence, text_of

SYSTEM = ("You are a precise classification specialist. You assign an item to exactly one "
          "category and never invent categories outside the given list.")


class Classify(Specialist):
    name = "classify"
    kind = "capability"
    contract = Contract(
        input={"item": object, "categories": list, "criteria": str},
        output={"label": str, "confidence": float, "reasoning": str},
    )

    def _run(self, input, config):
        categories = input["categories"]
        fs = block("classify", input)
        prompt = (
            f"Classify the ITEM into exactly one of these categories: {categories}\n"
            f"Decide by this criteria: {input['criteria']}\n\n"
            f"ITEM:\n{text_of(input['item'])}\n\n"
            + (fs + "\n\n" if fs else "")
            + 'Return JSON: {"label": <one category>, "confidence": <0..1>, '
              '"reasoning": <one short sentence>}'
        )
        r = brain_json(prompt, system=SYSTEM, temperature=0.0)
        label = str(r.get("label", "")).strip()
        if label not in categories:              # snap to nearest valid category
            label = _closest(label, categories)
        return {"label": label, "confidence": num(r.get("confidence")),
                "reasoning": one_sentence(r.get("reasoning"))}


def _closest(label: str, categories: list[str]) -> str:
    low = label.lower()
    for c in categories:
        if c.lower() in low or low in c.lower():
            return c
    return categories[-1]                        # fall back to the last (usually "other"/"spam")
