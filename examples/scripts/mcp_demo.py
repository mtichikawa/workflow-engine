"""MCP interop demo — the engine's symmetry, end to end, no brain needed.

  IMPORT : a real recipe step (the `mcp_call` specialist) calls a tool on an external MCP server (the
           test mock) and the result flows through the real dispatcher.
  EXPORT : an MCP client discovers the engine's specialists as MCP tools and calls one.

    pip install -e '.[mcp]'
    python examples/scripts/mcp_demo.py

Skips cleanly (exit 0) if the optional `mcp` dependency isn't installed, so a core-only install is fine.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _mcp_installed() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


MOCK = str(ROOT / "tests" / "mcp_mock_server.py")
MOCK_SERVER = {"command": sys.executable, "args": [MOCK]}


def import_demo():
    """A one-step workflow whose step calls an external MCP tool, run through the real dispatcher."""
    import engine.specialists  # noqa: F401  -- register the library
    from engine.core import Board, Dispatcher, Recipe, Step, Tracer

    print("\n=== IMPORT: a workflow step calls an external MCP tool ===")
    recipe = Recipe("mcp-import", steps=[
        Step(id="pull", specialist="mcp_call",
             config={"server": MOCK_SERVER, "tool": "top_items"},   # WHICH server + tool (static)
             inputs={"arguments": "payload"}),                       # tool args come from the work item
    ])
    board = Board("mcp-import", "mcp-demo-import")
    board.add_item("item", {"limit": 2})       # -> top_items(limit=2)
    Dispatcher(recipe, board, Tracer("mcp-demo-import")).run(auto_approve=True)
    print("  pull step output:", board.context["item"]["pull"])


def export_demo():
    """An MCP client discovers the engine's specialists as tools and calls one (act, brain-free)."""
    from engine.mcp.client import call_tool, list_tools

    print("\n=== EXPORT: an MCP client uses the engine's specialists as MCP tools ===")
    server = {"command": sys.executable, "args": ["-m", "engine.mcp.server"],
              "env": {**os.environ, "PYTHONPATH": str(ROOT)}}  # child finds the engine like this script does
    tools = sorted(t["name"] for t in list_tools(server))
    print(f"  The engine exposes {len(tools)} MCP tools:", tools)
    out = call_tool(server, "act", {"input": {
        "target": "file", "mode": "staged",
        "payload": {"content": "hello from an MCP client", "name": "mcp_demo.txt"}}})
    print("  called the engine's 'act' tool via MCP ->", out)


def main():
    if not _mcp_installed():
        print("mcp demo: skipped (install the optional dependency: pip install -e '.[mcp]')")
        return
    import_demo()
    export_demo()
    print("\nmcp demo: OK")


if __name__ == "__main__":
    main()
