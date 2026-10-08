"""A minimal, real Hacker News MCP server — bundled so the symmetry demo runs with ZERO secrets.

It exposes one tool, `top_stories`, backed by the public Hacker News Firebase API (no auth). It returns the
SAME item shape as the engine's native `fetch(source=hn)` specialist, so an external MCP tool and a native engine
specialist are drop-in interchangeable in a recipe — the point of examples/scripts/mcp_symmetry.py.

    python examples/mcp_servers/hn_server.py     # runs an MCP server on stdio
"""

import json
import urllib.request

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hacker-news", log_level="WARNING")


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "engine-mcp-demo"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


@mcp.tool()
def top_stories(limit: int = 5) -> list[dict]:
    """Return the current top `limit` Hacker News stories as {id, title, url, score} — matching the engine's
    fetch(source=hn) output shape."""
    ids = _get("https://hacker-news.firebaseio.com/v0/topstories.json")[:limit]
    out = []
    for sid in ids:
        it = _get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
        if not it:
            continue
        out.append({
            "id": str(it.get("id", sid)),
            "title": it.get("title", ""),
            "url": it.get("url", ""),
            "score": it.get("score", 0),
        })
    return out


if __name__ == "__main__":
    mcp.run()
