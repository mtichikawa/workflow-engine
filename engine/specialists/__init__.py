"""Register the library of specialists (one shared instance each).

Both recipes import these SAME objects — the five capability-specialists are literally
shared, so "reuse" is enforced structurally, not by convention.
"""

from ..core import register
from .act import Act
from .classify import Classify
from .fetch import Fetch
from .rank import Rank
from .respond import Respond
from .review import Review
from .route import Route
from .verify import Verify
from .write import Write

# five shared capability-specialists
FETCH = register(Fetch())
CLASSIFY = register(Classify())
RANK = register(Rank())
VERIFY = register(Verify())
ACT = register(Act())

# domain specialists
ROUTE = register(Route())
RESPOND = register(Respond())
WRITE = register(Write())
REVIEW = register(Review())

CAPABILITIES = ["fetch", "classify", "rank", "verify", "act"]
DOMAIN = ["route", "respond", "write", "review"]
