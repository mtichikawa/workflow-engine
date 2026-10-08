"""A minimal, real GitHub-issues MCP server — bundled so the triage demo runs with ZERO secrets.

It exposes one tool, `list_issues`, backed by GitHub's public REST API (unauthenticated: ~60 req/hr, plenty
for a demo). It returns the SAME item shape as the engine's native `fetch(source=github)` specialist, so the two
are drop-in interchangeable (that's the whole symmetry point).

    python examples/mcp_servers/github_issues_server.py     # runs an MCP server on stdio

This is intentionally tiny. For a production setup, point the demo at the official GitHub MCP server instead
(`npx -y @modelcontextprotocol/server-github`, needs GITHUB_PERSONAL_ACCESS_TOKEN) — it's the same `mcp_call`
config, just a different `server` dict. See docs/mcp.md.
"""

import json
import urllib.request

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("github-issues", log_level="WARNING")


def _get(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": "engine-mcp-demo", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


@mcp.tool()
def list_issues(repo: str, limit: int = 5) -> list[dict]:
    """Return up to `limit` OPEN issues of a public GitHub repo (e.g. 'modelcontextprotocol/servers').

    Each item: {id, title, body, url, labels}. Pull requests are filtered out (the issues endpoint mixes
    them in). Matches the engine's fetch(source=github) output shape.
    """
    per_page = min(100, limit * 4 + 10)   # over-fetch: the endpoint also returns PRs
    data = _get(f"https://api.github.com/repos/{repo}/issues?state=open&per_page={per_page}")
    out = []
    for i in data:
        if "pull_request" in i:
            continue
        if len(out) >= limit:
            break
        out.append({
            "id": str(i["number"]),
            "title": i.get("title", ""),
            "body": (i.get("body") or "")[:2000],
            "url": i.get("html_url", ""),
            "labels": [l["name"] for l in i.get("labels", [])],
        })
    return out


if __name__ == "__main__":
    mcp.run()
