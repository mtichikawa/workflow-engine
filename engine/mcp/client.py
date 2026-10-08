"""MCP client adapter — call a tool on any external MCP server, from sync engine code.

Edge-only + optional: the `mcp` SDK is imported lazily inside the functions, so importing this module is
cheap and a core install without `mcp` is unaffected until a tool is actually called.

The MCP SDK is async; engine specialists are sync (they run on the dispatcher's worker threads). Each call
opens a short-lived stdio connection, drives the async client to completion bounded by `timeout`, and
tears it down — stateless, so a hung server can never wedge a workflow.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any


def _import_mcp():
    try:
        from mcp import ClientSession, StdioServerParameters, stdio_client
    except ImportError as e:  # pragma: no cover - exercised only without the extra installed
        raise RuntimeError(
            "MCP support requires the optional dependency: pip install -e '.[mcp]'"
        ) from e
    return ClientSession, StdioServerParameters, stdio_client


def _params(server: dict):
    """server = {'command': 'python', 'args': [...], 'env': {...}, 'cwd': ...} — how to launch the MCP server."""
    _, StdioServerParameters, _ = _import_mcp()
    return StdioServerParameters(command=server["command"], args=server.get("args", []),
                                 env=server.get("env"), cwd=server.get("cwd"))


def call_tool(server: dict, tool: str, arguments: dict | None = None, timeout: float = 30.0) -> Any:
    """Connect to an external MCP server (stdio), call one tool, return its result.

    Returns the tool's structured output if it provides one, else its text content. Raises on a tool
    error or `timeout` so a failing/hung MCP call surfaces as a normal specialist failure.
    """
    ClientSession, _, stdio_client = _import_mcp()
    params = _params(server)

    async def _run():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments or {})
                return _unwrap(result)

    return _drive(_run(), timeout, f"call_tool({tool!r})")


def list_tools(server: dict, timeout: float = 30.0) -> list[dict]:
    """Discover the tools an external MCP server exposes: [{name, description}, ...]."""
    ClientSession, _, stdio_client = _import_mcp()
    params = _params(server)

    async def _run():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                return [{"name": t.name, "description": t.description or ""} for t in listed.tools]

    return _drive(_run(), timeout, "list_tools")


def _drive(coro, timeout: float, what: str):
    """Run an async MCP interaction to completion from sync code, bounded by `timeout`."""
    async def _bounded():
        try:
            return await asyncio.wait_for(coro, timeout)
        except asyncio.TimeoutError as e:
            raise RuntimeError(f"MCP {what} timed out after {timeout}s") from e

    return asyncio.run(_bounded())


def _unwrap(result) -> Any:
    """Normalize an MCP CallToolResult into a plain Python value."""
    if getattr(result, "isError", False):
        raise RuntimeError(f"MCP tool error: {_text(result)[:300]}")
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        # FastMCP wraps non-object returns as {"result": <value>}; unwrap that convenience shape.
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured
    # No structured content: many servers return JSON as text. Parse it when it clearly is JSON,
    # otherwise hand back the plain text (so a text tool still works).
    text = _text(result)
    stripped = text.strip()
    if stripped[:1] in ("{", "["):
        try:
            return json.loads(stripped)
        except ValueError:
            pass
    return text


def _text(result) -> str:
    parts = []
    for block in getattr(result, "content", []) or []:
        t = getattr(block, "text", None)
        if t is not None:
            parts.append(t)
    return "\n".join(parts)
