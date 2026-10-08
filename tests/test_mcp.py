"""MCP interop tests — the symmetry, real end-to-end over stdio (the protocol itself is not mocked).

  IMPORT (client) : the `mcp_call` specialist calls a tool on a mock external MCP server and returns its
                    result — the engine adopts an external MCP tool as a capability.
  EXPORT (server) : an MCP client discovers each engine specialist as its own MCP tool (plus
                    compose_and_run) and calls one — the engine publishes its specialists as MCP tools.

Both SKIP cleanly (pass, no error) if the optional `mcp` dependency isn't installed, so a core-only
install keeps the whole suite green. Bounded by a timeout so a stuck server can't wedge the suite.

    python tests/test_mcp.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MOCK = str(ROOT / "tests" / "mcp_mock_server.py")


def _mcp_installed() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


def test_client_mcp_call_specialist():
    """IMPORT: the mcp_call specialist calls a real MCP tool on the mock server and returns its result."""
    if not _mcp_installed():
        print("    skipped (optional 'mcp' dependency not installed)")
        return
    import engine.specialists  # noqa: F401  -- register the library
    from engine.core import get

    server = {"command": sys.executable, "args": [MOCK]}
    out = get("mcp_call").run(
        {"server": server, "tool": "top_items", "arguments": {"limit": 3}}, {})
    result = out["result"]
    assert isinstance(result, list) and len(result) == 3, f"expected 3 items, got {result!r}"
    assert result[0]["title"] == "item 1", f"unexpected shape: {result[0]!r}"
    print("    IMPORT: mcp_call -> 3 items from the mock MCP server")


def test_server_exports_specialists_as_tools():
    """EXPORT: each engine specialist is a discoverable MCP tool; one is callable (act, brain-free)."""
    if not _mcp_installed():
        print("    skipped (optional 'mcp' dependency not installed)")
        return
    from engine.mcp.client import call_tool, list_tools

    server = {"command": sys.executable, "args": ["-m", "engine.mcp.server"]}
    names = {t["name"] for t in list_tools(server)}
    # every library specialist is exported as a tool, plus the whole-workflow tool
    for expected in ("classify", "summarize", "forecast", "mcp_call", "act", "compose_and_run"):
        assert expected in names, f"The engine MCP server missing tool {expected!r}; has {sorted(names)}"

    # callable proof: invoke the exported `act` tool (brain-free, stages a file) through MCP
    out = call_tool(server, "act", {"input": {"target": "file", "mode": "staged",
                                              "payload": {"content": "mcp smoke test", "name": "mcp_smoke.txt"}}})
    assert isinstance(out, dict) and out.get("status") == "staged", f"act tool result: {out!r}"
    print(f"    EXPORT: {len(names)} engine tools discoverable; called 'act' -> {out['status']}")


def test_server_works_when_launched_from_a_readonly_dir():
    """Claude Desktop starts MCP servers in a read-only directory; the server must not write relative
    to that. Launch it from '/' and call a tool that writes (act stages a file)."""
    if not _mcp_installed():
        print("    skipped (optional 'mcp' dependency not installed)")
        return
    from engine.mcp.client import call_tool

    server = {"command": sys.executable, "args": ["-m", "engine.mcp.server"], "cwd": "/",
              "env": {**os.environ, "PYTHONPATH": str(ROOT)}}
    out = call_tool(server, "act", {"input": {"target": "file", "mode": "staged",
                                              "payload": {"content": "launched from /", "name": "mcp_smoke.txt"}}})
    assert isinstance(out, dict) and out.get("status") == "staged", f"act tool result: {out!r}"
    print("    EXPORT from a read-only launch dir: act -> staged")


if __name__ == "__main__":
    test_client_mcp_call_specialist()
    test_server_exports_specialists_as_tools()
    test_server_works_when_launched_from_a_readonly_dir()
    print("mcp: OK")
