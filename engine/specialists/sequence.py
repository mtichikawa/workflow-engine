"""sequence — capability specialist: put a set of items into their correct total ORDER.

Distinct from rank (which scores ONE item) and classify (one label): sequence takes a SET and returns
the whole ordering. Config-driven (the ordering criterion). Validated against a real known order
(e.g. historical events by their actual year), scored by rank correlation (Kendall tau).
"""

from __future__ import annotations

from ..core import Contract, Specialist, brain_json
from ..fewshot import block
from ._util import as_list, one_sentence, text_of


class Sequence(Specialist):
    name = "sequence"
    kind = "capability"
    description = (
        "Put a SET of items into their correct total order by a stated criterion. "
        "USE WHEN the output is an ordering/sequence (chronology, recipe steps, a priority order). "
        "NOT one label (->classify), one 0..1 score for a single item (->rank), one predicted "
        "outcome (->forecast). "
        "CONFIG-DRIVEN via {criteria} (what to order by) -- reuse for any ordering, don't clone. "
        "IN items,criteria -> OUT order,reasoning."
    )
    contract = Contract(
        input={"items": list, "criteria": str},
        output={"order": list, "reasoning": str},
    )

    def _run(self, input, config):
        items = input["items"]
        ids = [str(it.get("id")) for it in items]
        fs = block("sequence", input)
        listing = "\n".join(f'{it.get("id")}: {text_of(it.get("text"), 300)}' for it in items)
        prompt = (
            f"Put these items into the correct order by: {input['criteria']}\n"
            "Return every id exactly once, in the correct order.\n\n"
            f"ITEMS:\n{listing}\n\n"
            + (fs + "\n\n" if fs else "")
            + 'Return JSON: {"order": [<id>, ...], "reasoning": <one short sentence>}'
        )
        r = brain_json(prompt, system="You are an ordering specialist.", temperature=0.0)
        order = [str(x) for x in as_list(r.get("order")) if str(x) in ids]
        for i in ids:                                # ensure a full permutation (append any dropped)
            if i not in order:
                order.append(i)
        return {"order": order, "reasoning": one_sentence(r.get("reasoning"))}
