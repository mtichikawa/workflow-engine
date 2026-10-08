"""The engine as an MCP server — the EXPORT half of the symmetry: publish each engine specialist as an MCP tool.

Because a specialist and an MCP tool are the same shape (a named capability with typed in/out), the server
just loops over the library and exposes each one as a tool, plus a `compose_and_run` tool for whole
workflows. Run it with:  `python -m engine.mcp.server`  (stdio transport, for Claude Desktop / the `claude`
CLI / any MCP client).

Edge-only entry point: the `mcp` SDK is imported lazily; the core never imports this module; it reuses
only public core entry points (compose, Dispatcher, Board, get, all_specialists) — no core edits.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path


def build_server():
    """Build (but don't start) the engine MCP server. Kept importable for tests."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover - only without the extra installed
        raise RuntimeError(
            "The engine MCP server requires the optional dependency: pip install -e '.[mcp]'"
        ) from e

    import engine.specialists  # noqa: F401  -- register the library
    from engine.composer import compose
    from engine.core import Board, Dispatcher, Tracer, all_specialists, get

    server = FastMCP("engine", log_level="WARNING")

    # EXPORT each library specialist as its own MCP tool: name = specialist name, description = its card.
    # Specialists are SYNC (and one, mcp_call, itself drives asyncio); run them in a worker thread so they
    # never touch the server's running event loop. This also keeps a slow specialist from blocking the loop,
    # and lets the engine be a server and an MCP client at once (see examples/scripts/mcp_server_and_client.py).
    def _make_tool(spec_name: str):
        async def tool(input: dict, config: dict | None = None) -> dict:
            return await asyncio.to_thread(get(spec_name).run, input, config or {})
        return tool

    for name, spec in all_specialists().items():
        desc = (getattr(spec, "description", "") or f"Run the engine '{name}' specialist.")
        server.add_tool(_make_tool(name), name=name, description=desc)

    # A whole-workflow tool: plain-English job -> compose -> run -> results.
    @server.tool()
    async def compose_and_run(use_case: str, input: str, scope: str | None = None) -> dict:
        """Describe a job in plain English; the engine composes a workflow from its library, runs it on
        `input`, and returns each step's output. `scope` optionally selects a tenant's tailored examples."""
        def _work() -> dict:
            from engine import scope as scope_mod
            token = scope_mod.set_scope(scope) if scope else None
            try:
                res = compose(use_case)
                if not res.get("runnable"):
                    return {"error": "not runnable from the current library",
                            "missing": res.get("missing"), "errors": res.get("errors")}
                run_id = "mcp-" + uuid.uuid4().hex[:8]
                board = Board("composed", run_id)
                board.add_item("item", {"text": input, "topic": input, "message": input})
                Dispatcher(res["recipe"], board, Tracer(run_id)).run(auto_approve=True)
                return {"run_id": run_id,
                        "steps": [s.get("id") for s in res.get("steps", [])],
                        "result": board.context.get("item", {})}
            finally:
                if token is not None:
                    scope_mod.reset_scope(token)
        return await asyncio.to_thread(_work)

    return server


def _home() -> Path:
    """Where the engine's working-dir-relative stores (state/, output/, logs/, private/) live.

    MCP clients launch servers from a directory of their choosing — Claude Desktop uses one that is
    read-only — so the server can't trust its inherited cwd. ENGINE_HOME wins; else the source checkout
    this package runs from (the normal `pip install -e .` case); else the inherited cwd."""
    if os.environ.get("ENGINE_HOME"):
        return Path(os.environ["ENGINE_HOME"]).expanduser().resolve()
    checkout = Path(__file__).resolve().parents[2]
    if (checkout / "pyproject.toml").is_file() and (checkout / "engine").is_dir():
        return checkout
    return Path.cwd()


def main():
    home = _home()
    if not (home.is_dir() and os.access(home, os.W_OK)):
        # stderr, not stdout: stdout is the MCP protocol channel
        sys.exit(f"engine MCP server: {home} is not a writable directory — set ENGINE_HOME to one")
    os.chdir(home)
    build_server().run()   # stdio transport by default


if __name__ == "__main__":
    main()
