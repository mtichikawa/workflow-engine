"""The recipes. Both draw from the same specialist library."""

from .content import CONTENT
from .refine import REFINE
from .review import REVIEW
from .triage import TRIAGE

RECIPES = {r.name: r for r in (TRIAGE, CONTENT, REVIEW, REFINE)}
