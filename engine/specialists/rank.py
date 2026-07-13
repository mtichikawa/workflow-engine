"""rank — capability specialist: score one item on a criterion (0..1).

Ranking = per-item scoring here, then a mechanical sort at presentation time. That
keeps everything per-item (no cross-item aggregation), so it fans out and parallelizes
cleanly. Config `scoring` differs per recipe (urgency for triage, resonance for content);
the specialist is identical.
"""

from __future__ import annotations

from ..core import Contract, Specialist, brain_json
from ..fewshot import block
from ._util import num, one_sentence, text_of

SYSTEM = ("You are a scoring specialist. You rate a single item from 0 to 1 on a stated "
          "dimension, calibrated and consistent.")


class Rank(Specialist):
    name = "rank"
    kind = "capability"
    contract = Contract(
        input={"item": object, "scoring": str},
        output={"score": float, "reasoning": str},
    )

    def _run(self, input, config):
        fs = block("rank", input)
        prompt = (
            f"Score the ITEM from 0.0 to 1.0 on this dimension: {input['scoring']}\n"
            "0 = lowest, 1 = highest. Be calibrated.\n\n"
            f"ITEM:\n{text_of(input['item'])}\n\n"
            + (fs + "\n\n" if fs else "")
            + 'Return JSON: {"score": <0..1>, "reasoning": <one short sentence>}'
        )
        r = brain_json(prompt, system=SYSTEM, temperature=0.0)
        score = max(0.0, min(1.0, num(r.get("score"))))
        return {"score": score, "reasoning": one_sentence(r.get("reasoning"))}
