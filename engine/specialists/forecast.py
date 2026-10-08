"""forecast — capability specialist: predict an uncertain FUTURE outcome from earlier state.

Distinct from classify: classify labels what an item already IS (readable from the item); forecast
commits to an outcome that is NOT determinable from the input and is only revealed later. Config-driven
(the outcome space), low temperature. Validated by reality: leave-one-out over historical situations
whose real outcome is known.
"""

from __future__ import annotations

from ..core import Contract, Specialist, brain_json
from ..fewshot import block
from ._util import num, one_sentence, text_of

SYSTEM = ("You are a forecasting specialist. From earlier, INCOMPLETE information you predict a future "
          "outcome that is not yet known. Commit to exactly one listed outcome and give a calibrated "
          "confidence; never hedge across several.")


class Forecast(Specialist):
    name = "forecast"
    kind = "capability"
    description = (
        "Predict an UNKNOWN / future outcome from earlier, incomplete information. "
        "USE WHEN the answer is NOT determinable from the item itself but is revealed later "
        "(a game result, will-this-bill-pass, will-this-customer-churn). "
        "NOT categorizing what something already IS (->classify), scoring a dimension (->rank). "
        "CONFIG-DRIVEN via {outcomes} -- reuse for any outcome space, don't clone. "
        "IN situation,outcomes -> OUT prediction,confidence,reasoning."
    )
    contract = Contract(
        input={"situation": object, "outcomes": list},
        output={"prediction": str, "confidence": float, "reasoning": str},
    )

    def _run(self, input, config):
        outcomes = input["outcomes"]
        fs = block("forecast", input)
        prompt = (
            f"Predict the single most likely outcome from exactly these: {outcomes}\n"
            "You are given only the information available BEFORE the outcome is known.\n\n"
            f"SITUATION:\n{text_of(input['situation'])}\n\n"
            + (fs + "\n\n" if fs else "")
            + 'Return JSON: {"prediction": <one outcome>, "confidence": <0..1>, '
              '"reasoning": <one short sentence>}'
        )
        r = brain_json(prompt, system=SYSTEM, temperature=0.0)
        pred = str(r.get("prediction", "")).strip()
        if pred not in outcomes:                     # snap to nearest valid outcome
            low = pred.lower()
            pred = next((o for o in outcomes if o.lower() in low or low in o.lower()), outcomes[0])
        return {"prediction": pred, "confidence": num(r.get("confidence")),
                "reasoning": one_sentence(r.get("reasoning"))}
