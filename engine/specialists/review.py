"""review — DOMAIN specialist (code review): read a PR + diff, flag concrete issues.

The only new specialist the third recipe needs — everything else is reused. That small
delta IS the compounding: recipe #3 is mostly parts the library already had.
"""

from __future__ import annotations

from ..core import Contract, Specialist, brain_json
from ._util import as_list, text_of

SYSTEM = ("You are a careful senior code reviewer. You flag concrete, actionable issues "
          "(bugs, security, missing tests, breaking changes) and skip style nitpicks.")


class Review(Specialist):
    name = "review"
    kind = "domain"
    contract = Contract(
        input={"item": object, "checklist": str},
        output={"risk": str, "findings": list, "comment": str},
    )

    def _run(self, input, config):
        prompt = (
            f"Review this pull request against: {input['checklist']}\n\n"
            f"PR:\n{text_of(input['item'], limit=6000)}\n\n"
            'Return JSON: {"risk": "low"|"medium"|"high", '
            '"findings": [<short concrete issue strings>], '
            '"comment": <a concise reviewer comment summarizing the findings>}'
        )
        r = brain_json(prompt, system=SYSTEM, temperature=0.0)
        risk = str(r.get("risk", "medium")).lower()
        risk = risk if risk in ("low", "medium", "high") else "medium"
        return {"risk": risk,
                "findings": [str(x) for x in as_list(r.get("findings"))],
                "comment": str(r.get("comment", "")).strip()}
