"""extract — capability specialist: pull a set of structured facts out of unstructured prose.

Distinct from classify (which picks ONE label) and from rank/verify: extract returns a LIST of items
of a requested kind that appear in the text. Config-driven (what to extract), low temperature.
Validated against real structured data that was published alongside the prose (e.g. a recipe's
ingredient list vs. its free-text instructions).
"""

from __future__ import annotations

from ..core import Contract, Specialist, brain_json
from ..fewshot import block
from ._util import as_list, one_sentence, text_of

SYSTEM = ("You are an extraction specialist. You pull out exactly the requested kind of item that "
          "actually appears in the text, as a clean list of short canonical names — no quantities, "
          "no duplicates, nothing not present in the text.")


class Extract(Specialist):
    name = "extract"
    kind = "capability"
    description = (
        "Pull a LIST of structured facts of a requested kind out of unstructured prose. "
        "USE WHEN you need the set of things mentioned in a text (ingredients in instructions, "
        "entities in an article, line-items in a note). "
        "NOT picking one label (->classify), scoring (->rank), pass/fail (->verify). "
        "CONFIG-DRIVEN via {target} (what to pull) -- reuse for any extraction, don't clone. "
        "IN text,target -> OUT items,reasoning."
    )
    contract = Contract(
        input={"text": object, "target": str},
        output={"items": list, "reasoning": str},
    )

    def _run(self, input, config):
        fs = block("extract", input)
        prompt = (
            f"From the TEXT below, extract every {input['target']}.\n"
            "Return each as a short canonical name (lowercase, no quantities/units), no duplicates, "
            "and include ONLY things actually present in the text.\n\n"
            f"TEXT:\n{text_of(input['text'])}\n\n"
            + (fs + "\n\n" if fs else "")
            + 'Return JSON: {"items": [<name>, ...], "reasoning": <one short sentence>}'
        )
        r = brain_json(prompt, system=SYSTEM, temperature=0.0)
        items, seen = [], set()
        for x in as_list(r.get("items")):
            name = str(x).strip().lower()
            if name and name not in seen:
                seen.add(name)
                items.append(name)
        return {"items": items, "reasoning": one_sentence(r.get("reasoning"))}
