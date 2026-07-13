"""Refine recipe — draft → verify → (revise → verify)* → publish. The LOOP showcase.

Per work-item = one topic with a STRICT brief. `write` drafts; `verify` checks it against the
brief; if it fails, a backward edge loops back to `write` to revise (verify's issues are kept as
feedback), bounded by `max_visits`; when it passes, it flows to the gated `act`. This is the
control-flow graph doing a real quality-refinement loop on live generation — the loop is visible
in `engine replay` (tokens flowing back through write↔verify before publishing).

Reuses the shared library (write/verify/act) — only the graph shape is new.
"""

from engine.core import Edge, Recipe, Step

REFINE = Recipe(name="refine", max_visits=4, steps=[
    Step(id="write", specialist="write", domain=True,
         inputs={"topic": "payload.topic", "sources": "payload.sources", "brief": "payload.brief",
                 "feedback": "verify.issues"}),        # None on first pass; verify's issues on a loop

    Step(id="verify", specialist="verify",
         inputs={"subject": {"draft": "write.post", "topic": "payload.topic"}},
         config={"standard": "STRICT — fail unless ALL hold: contains AT LEAST TWO distinct "
                            "concrete numeric statistics (real numbers, percentages, or units); "
                            "names a specific, concrete failure mode; uses NO hype words "
                            "(revolutionary, game-changing, seamless, powerful, robust); no emojis; "
                            "under 4 sentences. Be demanding — flag every miss in `issues`."}),

    Step(id="act", specialist="act", gate=True,
         inputs={"payload": {"content": "write.post", "name": "payload.slug"}},
         config={"target": "file", "mode": "staged"}),
], edges=[
    Edge("write", "verify"),
    Edge("verify", "write", "verify.verdict == 'fail'"),   # LOOP: revise until it passes (guarded)
    Edge("verify", "act", "verify.verdict == 'pass'"),     # then publish (gated)
])
