"""summarize — capability specialist: compress a long text into a short, faithful summary.

Distinct from extract (a list of items) and classify (a label): summarize produces free-text in a
requested short form (a title, a headline, a one-liner). Config-driven (the target form). Validated
against a real human-written short form published beside the long text (e.g. a paper's title vs its
abstract), scored by lexical recall of the reference's key words.
"""

from __future__ import annotations

from ..core import Contract, Specialist, brain_json
from ..fewshot import block
from ._util import text_of


class Summarize(Specialist):
    name = "summarize"
    kind = "capability"
    description = (
        "Compress a long text into a short, faithful summary of a requested form. "
        "USE WHEN you need a title/headline/abstract/one-liner distilled from longer prose. "
        "NOT pulling a list of items (->extract), a label (->classify), a score (->rank). "
        "CONFIG-DRIVEN via {brief} (the target form/length) -- reuse for any summary style, don't clone. "
        "IN text,brief -> OUT summary."
    )
    contract = Contract(
        input={"text": object, "brief": str},
        output={"summary": str},
    )

    def _run(self, input, config):
        fs = block("summarize", input)
        prompt = (
            f"Summarize the TEXT as: {input['brief']}\n"
            "Keep only the core; add nothing that is not in the text.\n\n"
            f"TEXT:\n{text_of(input['text'])}\n\n"
            + (fs + "\n\n" if fs else "")
            + 'Return JSON: {"summary": <the summary text>}'
        )
        r = brain_json(prompt, system="You are a summarization specialist.", temperature=0.0)
        return {"summary": " ".join(str(r.get("summary", "")).split())}
