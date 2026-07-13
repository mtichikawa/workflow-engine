"""Code-review recipe (recipe #3) — proves compounding.

Same skeleton, reuses classify/rank/verify/act; the only new part is the `review`
middle. A third domain stood up in a fraction of the code the first two took.
"""

from engine.core import Edge, Recipe, Step

CHANGE_TYPES = ["feature", "bugfix", "refactor", "docs", "test", "chore"]

REVIEW = Recipe(name="review", steps=[
    Step(id="classify", specialist="classify",
         inputs={"item": "payload"},
         config={"categories": CHANGE_TYPES, "criteria": "the kind of change in this PR"}),

    Step(id="rank", specialist="rank",
         inputs={"item": "payload"},
         config={"scoring": "review priority: touches security/auth/data or core > broad change "
                            "> small or docs-only"}),

    Step(id="review", specialist="review", domain=True,
         inputs={"item": "payload"},
         config={"checklist": "correctness, security, missing tests, breaking changes; "
                            "skip style nitpicks"}),

    Step(id="verify", specialist="verify",
         inputs={"subject": {"findings": "review.findings", "comment": "review.comment"}},
         config={"standard": "the findings are concrete and actionable, not vague or nitpicks"}),

    Step(id="act", specialist="act", gate=True,
         inputs={"payload": {"labels": ["classify.label"],
                            "comment": "review.comment",
                            "url": "payload.url",
                            "priority": "rank.score"}},
         config={"target": "github", "mode": "staged"}),
], edges=[
    Edge("classify", "rank"), Edge("rank", "review"), Edge("review", "verify"),
    Edge("verify", "act", "verify.verdict == 'pass'"),   # only stage the review comment if it holds up
])
