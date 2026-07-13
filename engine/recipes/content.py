"""Content recipe (light) — proves REUSE.

Per work-item = one topic. It calls the SAME fetch/classify/rank/verify/act instances
as triage; only the middle (`write`) is domain. Light text output so the proof doesn't
need the heavy video pipeline.
"""

from engine.core import Edge, Recipe, Step

ANGLES = ["how-to", "opinion", "news", "analysis", "announcement"]

CONTENT = Recipe(name="content", steps=[
    Step(id="fetch", specialist="fetch",
         inputs={"source": "payload.source", "params": "payload"}),

    Step(id="classify", specialist="classify",
         inputs={"item": "payload.topic"},
         config={"categories": ANGLES, "criteria": "the best content angle for this topic"}),

    Step(id="rank", specialist="rank",
         inputs={"item": "payload.topic"},
         config={"scoring": "resonance and shareability for a technical audience"}),

    Step(id="write", specialist="write", domain=True,
         inputs={"topic": "payload.topic", "sources": "fetch.items", "brief": "payload.brief"}),

    Step(id="verify", specialist="verify",
         inputs={"subject": {"draft": "write.post", "topic": "payload.topic"}},
         config={"standard": "on-brand (no hype, no emojis, numbers over adjectives), coherent, "
                            "and not making unsupported factual claims"}),

    Step(id="act", specialist="act", gate=True,
         inputs={"payload": {"content": "write.post", "name": "payload.slug",
                            "angle": "classify.label", "priority": "rank.score"}},
         config={"target": "file", "mode": "staged"}),
], edges=[
    Edge("fetch", "classify"), Edge("classify", "rank"), Edge("rank", "write"),
    Edge("write", "verify"),
    Edge("verify", "act", "verify.verdict == 'pass'"),   # only stage the post if it passes review
])
