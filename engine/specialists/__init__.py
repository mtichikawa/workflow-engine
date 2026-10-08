"""Register the library of specialists (one shared instance each).

Both recipes import these SAME objects — the five capability-specialists are literally
shared, so "reuse" is enforced structurally, not by convention.
"""

from ..core import register
from .act import Act
from .classify import Classify
from .extract import Extract
from .fetch import Fetch
from .forecast import Forecast
from .match import Match
from .mcp_call import McpCall
from .rank import Rank
from .respond import Respond
from .review import Review
from .route import Route
from .sequence import Sequence
from .summarize import Summarize
from .verify import Verify
from .write import Write

# five shared capability-specialists
FETCH = register(Fetch())
CLASSIFY = register(Classify())
RANK = register(Rank())
VERIFY = register(Verify())
ACT = register(Act())
MCP_CALL = register(McpCall())         # I/O adapter: call any external MCP tool (optional mcp dep)
FORECAST = register(Forecast())
EXTRACT = register(Extract())
SUMMARIZE = register(Summarize())
SEQUENCE = register(Sequence())
MATCH_SP = register(Match())

# domain specialists
ROUTE = register(Route())
RESPOND = register(Respond())
WRITE = register(Write())
REVIEW = register(Review())

CAPABILITIES = ["fetch", "classify", "rank", "verify", "act", "mcp_call", "forecast", "extract",
                "summarize", "sequence", "match"]
DOMAIN = ["route", "respond", "write", "review"]
