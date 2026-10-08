"""USE CASE C — the engine as an MCP server AND an MCP client at the same time.

The process tree at the peak of this demo is three deep:

    this script (an MCP client)
        └── the engine's MCP server            <- the engine is a SERVER here (answering our tool calls)
                └── filesystem MCP server  <- ...and a CLIENT here (the engine calls out via its mcp_call tool)

So the exact same engine process is simultaneously serving tools to us and consuming a tool from someone else.
That is the symmetry from examples/scripts/mcp_symmetry.py taken to its conclusion: import and export are two ends of
one shape.

Flow:
  1. We ask the engine's `mcp_call` tool to read a file — the engine relays that to the OFFICIAL filesystem MCP server
     (`npx @modelcontextprotocol/server-filesystem`, a real third-party server) and hands us back the content.
  2. We ask the engine's `summarize` tool to reason over that content — the engine's own specialist, its own brain.

Runs with zero secrets (filesystem server needs only an allowed directory).

    pip install -e '.[mcp]'
    python examples/scripts/mcp_server_and_client.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DEMO_DIR = Path("/tmp/engine-mcp-demo")
NOTE = DEMO_DIR / "release-note.txt"

# Real content to reason over (a self-describing note, so the summary is meaningful and verifiable).
NOTE_TEXT = (
    "Engine release note — MCP interop.\n\n"
    "The engine is a workflow-automation engine: small AI specialists (classify, route, summarize, forecast, "
    "extract, and more) composed into recipes and run on a board by a dependency-scheduling dispatcher. "
    "With the optional MCP layer, the engine can import any external MCP tool as a specialist via `mcp_call`, "
    "and export every one of its own specialists as an MCP tool through `python -m engine.mcp.server`. "
    "Because a specialist and an MCP tool are the same shape, a single engine process can serve tools to one "
    "client while calling out to another server in the middle of the same workflow."
)

ENGINE = {"command": sys.executable, "args": ["-m", "engine.mcp.server"],
          "env": {**os.environ, "PYTHONPATH": str(ROOT)}}  # child finds the engine like this script does
FS_SERVER = {"command": "npx",
             "args": ["-y", "@modelcontextprotocol/server-filesystem", str(DEMO_DIR)]}


def _mcp_installed() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


def main():
    if not _mcp_installed():
        print("skipped (install the optional dependency: pip install -e '.[mcp]')")
        return
    from engine.mcp.client import call_tool

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    NOTE.write_text(NOTE_TEXT)
    print(f"wrote {NOTE} ({len(NOTE_TEXT)} bytes)\n")

    print("=== step 1: call the engine's `mcp_call` tool -> the engine relays to the filesystem MCP server ===")
    read = call_tool(ENGINE, "mcp_call", {"input": {
        "server": FS_SERVER, "tool": "read_text_file", "arguments": {"path": str(NOTE)}}}, timeout=90)
    content = read["result"] if isinstance(read, dict) and "result" in read else read
    if isinstance(content, dict):                      # some servers nest text under a key
        content = content.get("text") or next(iter(content.values()), "")
    print(f"  The engine (as client) read {len(str(content))} bytes back from the filesystem server\n")

    print("=== step 2: call the engine's `summarize` tool -> the engine's own specialist reasons over it ===")
    out = call_tool(ENGINE, "summarize", {"input": {
        "text": str(content), "brief": "one sentence, for a changelog"}}, timeout=90)
    summary = out.get("summary") if isinstance(out, dict) else out
    print(f"  summary: {summary}\n")

    print("One engine process just acted as a server (to us) and a client (to filesystem) in a single run.")


if __name__ == "__main__":
    main()
