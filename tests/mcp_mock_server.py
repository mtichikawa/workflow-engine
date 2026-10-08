"""A tiny mock MCP server used by the client-adapter test.

Stands in for any external MCP server. Exposes one tool, so the test can prove the engine's `mcp_call`
specialist calls a real MCP tool over stdio and uses the result.

    python tests/mcp_mock_server.py      # runs an MCP server on stdio
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("engine-mock", log_level="WARNING")


@mcp.tool()
def top_items(limit: int = 3) -> list[dict]:
    """Return `limit` fake items (id + title)."""
    return [{"id": str(i), "title": f"item {i}"} for i in range(1, limit + 1)]


if __name__ == "__main__":
    mcp.run()
