"""Triage recipe — a support/issue triager.

Per work-item = one GitHub issue. Shared capability-specialists do the bookends
(classify, rank, verify, act); route + respond are the domain middle. `act` is gated
and staged (never posts to the real repo).
"""

from engine.core import Edge, Recipe, Step

CATEGORIES = ["bug", "feature", "question", "duplicate", "spam"]
COMPONENTS = ["core", "api", "docs", "build", "ui", "auth", "other"]

TRIAGE = Recipe(name="triage", steps=[
    Step(id="classify", specialist="classify",
         inputs={"item": "payload"},
         config={"categories": CATEGORIES, "criteria": "the kind of issue"}),

    Step(id="rank", specialist="rank",
         inputs={"item": "payload"},
         config={"scoring": "urgency: security or data-loss or outage > blocks many users "
                            "> broken feature > nice-to-have"}),

    Step(id="route", specialist="route", domain=True,
         inputs={"item": "payload"},
         config={"components": COMPONENTS}),

    Step(id="respond", specialist="respond", domain=True,
         inputs={"item": "payload"},
         config={"tone": "helpful, concise, no promised timelines"}),

    Step(id="verify", specialist="verify",
         inputs={"subject": {"issue_title": "payload.title",
                             "classified_as": "classify.label",
                             "routed_to": "route.component",
                             "draft_reply": "respond.reply"}},
         config={"standard": "the classification and routing fit the issue, and the reply "
                            "is relevant and asks for anything genuinely missing"}),

    Step(id="act", specialist="act", gate=True,
         inputs={"payload": {"labels": ["classify.label", "route.component"],
                            "comment": "respond.reply",
                            "url": "payload.url",
                            "priority": "rank.score"}},
         config={"target": "github", "mode": "staged"}),
], edges=[
    Edge("classify", "rank"), Edge("rank", "route"), Edge("route", "respond"),
    Edge("respond", "verify"),
    # verify is ADVISORY, not a hard gate: it never blocks. Both outcomes stage for a human —
    # a fail is staged flagged (its verdict + concerns ride along) rather than silently dropped.
    Edge("verify", "act", "verify.verdict == 'pass'"),   # checks out → stage normally
    Edge("verify", "act", "verify.verdict == 'fail'"),   # doesn't check out → still stage, flagged for a human
])
