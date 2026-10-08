"""match — capability specialist: decide whether TWO items are the same / belong together.

The pairwise capability (dedup, entity-resolution, linking): input is a PAIR, output is one boolean.
Distinct from classify (labels ONE item), rank (scores ONE), sequence (orders a SET). Config-driven
(what "same" means). Validated against real pair labels (e.g. whether two questions came from the same
community).
"""

from __future__ import annotations

from ..core import Contract, Specialist, brain_json
from ..fewshot import block
from ._util import num, one_sentence, text_of


class Match(Specialist):
    name = "match"
    kind = "capability"
    description = (
        "Decide whether TWO items are the same / belong together -- a pairwise comparison. "
        "USE WHEN deduping, entity-resolution, linking, or answering 'are these the same?' (input is a PAIR). "
        "NOT labeling one item (->classify), scoring one item (->rank), ordering a set (->sequence). "
        "CONFIG-DRIVEN via {criteria} (what 'same' means) -- reuse for any match, don't clone. "
        "IN a,b,criteria -> OUT same,confidence,reasoning."
    )
    contract = Contract(
        input={"a": object, "b": object, "criteria": str},
        output={"same": bool, "confidence": float, "reasoning": str},
    )

    def _run(self, input, config):
        fs = block("match", input)
        prompt = (
            f"Decide whether these two items are the same / belong together by: {input['criteria']}\n\n"
            f"ITEM A:\n{text_of(input['a'])}\n\nITEM B:\n{text_of(input['b'])}\n\n"
            + (fs + "\n\n" if fs else "")
            + 'Return JSON: {"same": <true|false>, "confidence": <0..1>, "reasoning": <one short sentence>}'
        )
        r = brain_json(prompt, system="You are a pairwise-matching specialist.", temperature=0.0)
        return {"same": bool(r.get("same")), "confidence": num(r.get("confidence")),
                "reasoning": one_sentence(r.get("reasoning"))}
