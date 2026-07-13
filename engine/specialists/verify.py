"""verify — capability specialist: pressure-test a claim or a prior decision.

Reused everywhere (triage: is the triage decision sound? content: is the draft
supported and on-brand?). Config `standard` states what "good" means.
"""

from __future__ import annotations

from ..core import Contract, Specialist, brain_json
from ..fewshot import block
from ._util import as_list, num, text_of

SYSTEM = ("You are a skeptical verification specialist. You check whether a subject meets a "
          "stated standard, default to flagging problems, and never rubber-stamp.")


class Verify(Specialist):
    name = "verify"
    kind = "capability"
    contract = Contract(
        input={"subject": object, "standard": str},
        output={"verdict": str, "confidence": float, "issues": list},
    )

    def _run(self, input, config):
        # verify calls block() like every other specialist; whether few-shot is actually injected
        # is decided by the EMPIRICAL cached policy (fewshot.policy_on <- `engine fit`). verify is a
        # checker — similar subjects have uncorrelated verdicts, so the fit eval turns few-shot OFF
        # for it (LOO does worse with it). That's mapper-vs-checker emerging from data, not asserted.
        fs = block("verify", input)
        prompt = (
            f"Judge whether the SUBJECT meets this standard: {input['standard']}\n\n"
            f"SUBJECT:\n{text_of(input['subject'])}\n\n"
            + (fs + "\n\n" if fs else "")
            + 'Return JSON: {"verdict": "pass" or "fail", "confidence": <0..1>, '
              '"issues": [<zero or more short problem strings>]}'
        )
        r = brain_json(prompt, system=SYSTEM, temperature=0.0)
        verdict = "pass" if str(r.get("verdict", "")).lower().startswith("pass") else "fail"
        return {"verdict": verdict, "confidence": num(r.get("confidence")),
                "issues": [str(x) for x in as_list(r.get("issues"))]}
