# MCP interop (edge-only, symmetric)

The engine speaks the [Model Context Protocol](https://modelcontextprotocol.io) on **both** sides. The clean
framing: **an engine specialist and an MCP tool are the same shape** — a named capability with typed inputs
and outputs — so interop is just mapping between the two, in both directions.

- **IMPORT (client)** — the `mcp_call` specialist adopts any external MCP tool as an engine capability.
- **EXPORT (server)** — `engine.mcp.server` publishes each engine specialist as an MCP tool.

Honest one-liner: **the engine consumes MCP tools and exposes its workflows as MCP tools.** Real interop, a
genuine capability — not novel research.

## Design: it lives at the edges

All MCP code is in `engine/mcp/` plus one new library specialist (`mcp_call`). It imports **from** the core;
the core never imports it. **No changes to the core interfaces** (composer, specialist contracts,
dispatcher, resolver) — and `fetch` is untouched. The engine behaves identically with MCP absent.

- **Optional dependency.** The `mcp` SDK is an extra: `pip install -e '.[mcp]'`. A core install doesn't
  need it. `mcp_call` registers fine without it and only needs it at run time.
- **Lazy-imported.** The SDK is imported *inside* the functions that use it. Nothing MCP loads unless you
  actually call an MCP tool or start the server (verified: importing `engine`, the specialists, even
  `engine.mcp.*` does not load the SDK).
- **Sync over async.** The SDK is async; specialists are sync (dispatcher worker threads). The client
  adapter opens a short-lived stdio connection per call, bounded by a `timeout` so a hung server can't
  wedge a workflow. On the **server** side each specialist runs via `asyncio.to_thread`, so a sync (or
  itself-async, like `mcp_call`) specialist never touches the server's event loop — which is what lets
  the engine be a server and an MCP client *at the same time* (use case C below).

## IMPORT — the engine as MCP client (`mcp_call` specialist)

`mcp_call` is an I/O-adapter specialist (like `fetch`/`act`): pure plumbing, no brain, no golds. It calls
a named tool on any MCP server and returns its result.

- **Contract:** `IN {server, tool, arguments} -> OUT {result}`.
- **In a recipe:** a step with `specialist="mcp_call"`, `config={"server": ..., "tool": ...}` (which
  server + tool), `inputs={"arguments": ...}` (the live tool arguments).

```python
from engine.core import get
import engine.specialists  # register the library

out = get("mcp_call").run({
    "server": {"command": "python", "args": ["path/to/some_mcp_server.py"]},
    "tool": "top_items",
    "arguments": {"limit": 3},
}, {})
# out["result"] -> whatever the tool returned (a list, dict, value, ...)
```

`engine/mcp/client.py` also exposes `list_tools(server)` to discover a server's tools.

## EXPORT — the engine as MCP server (each specialist is a tool)

Run it (stdio transport, for Claude Desktop / the `claude` CLI / any MCP client):

```bash
pip install -e '.[mcp]'
python -m engine.mcp.server
```

It exposes **every library specialist as its own MCP tool** (name = specialist name, description = its
capability card), plus a whole-workflow tool:

| Tool | What it does |
|---|---|
| `classify`, `summarize`, `forecast`, `extract`, `rank`, `verify`, `sequence`, `match`, `route`, `respond`, `write`, `review`, `fetch`, `act`, `mcp_call` | run that specialist directly: `input` (dict), optional `config` |
| `compose_and_run(use_case, input, scope=None)` | plain-English job → compose a workflow → run it on `input` → return each step's output |

Example Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "engine": { "command": "python", "args": ["-m", "engine.mcp.server"] }
  }
}
```

## Worked use cases (all runnable, real data, zero secrets)

Four demos, each proving a different thing. A/B/C run end-to-end today against real public data (the first
three were verified live on 2026-07-28); D needs Claude Desktop and ~2 minutes of your hands. They share two
tiny **bundled example MCP servers** (`examples/mcp_servers/`) — a GitHub-issues server and a Hacker News
server, each ~40 lines of stdlib over a public API, returning the *same item shape* as the engine's native
`fetch` — so every demo works with no keys. Swap in an official/token server by changing one `server` dict.

### A. Triage a live GitHub issue tracker — `examples/scripts/mcp_github_triage.py`
An **external MCP tool does the I/O, the engine does the reasoning.** Phase 1: an `mcp_call` step pulls real open
issues via the GitHub-issues MCP server. Phase 2: each issue is `classify`d (bug/feature/docs/security),
`route`d to a component, and `summarize`d — one board card per issue, on the real dispatcher.
```bash
python examples/scripts/mcp_github_triage.py modelcontextprotocol/servers 4
```
To use the **official** GitHub MCP server instead, set the `server` dict to
`{"command":"npx","args":["-y","@modelcontextprotocol/server-github"],"env":{"GITHUB_PERSONAL_ACCESS_TOKEN":"…"}}`.
This is the "reasoning agent over a live tracker" shape.

### B. Symmetry made visible — `examples/scripts/mcp_symmetry.py`
Pulls the current Hacker News top stories **two ways** — the engine's native `fetch(source=hn)` specialist *and*
an external MCP `top_stories` tool — shows the item shapes are byte-identical, then runs the **same** classify
step on each. Proof that "a specialist and an MCP tool are the same shape": the recipe tail doesn't care
which supplied the data.
```bash
python examples/scripts/mcp_symmetry.py 3
```

### C. The engine as server AND client at once — `examples/scripts/mcp_server_and_client.py`
A three-deep process tree: this script (client) → the engine's MCP server → the **official** filesystem MCP server
(`npx @modelcontextprotocol/server-filesystem`). We call the engine's `mcp_call` tool to read a file (the engine relays
to filesystem — the engine is a *client* here), then the engine's `summarize` tool to reason over it (the engine is a
*server* here). One process, both roles, one run.
```bash
python examples/scripts/mcp_server_and_client.py
```

### D. Drive the engine live from Claude Desktop — needs your hands (~2 min)
This is the flagship "it's real, not a harness" proof: expose the engine's tools inside Claude Desktop and let
*its* model call them.

1. Install the extra in the environment Claude Desktop will launch: `pip install -e '.[mcp]'`.
2. Get the absolute interpreter path: `python -c "import sys; print(sys.executable)"`.
3. Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) and add:
   ```json
   {
     "mcpServers": {
       "engine": { "command": "/ABSOLUTE/PATH/TO/python", "args": ["-m", "engine.mcp.server"] }
     }
   }
   ```
   Use the absolute path from step 2 — Claude Desktop doesn't inherit your shell's `PATH`/venv.
   Two things the server handles itself, because Desktop launches it from a read-only directory with a
   minimal `PATH`: it works from the source checkout it runs from (override with `"env": {"ENGINE_HOME":
   "/path/to/workflow-engine"}`), and it finds the `claude` CLI in its standard install locations
   (override with `"ENGINE_CLAUDE_BIN": "/path/to/claude"` in the same `env`).
4. Fully quit and reopen Claude Desktop. The engine's tools appear under the tools (plug) icon.
5. Try: *"Use the engine's `classify` tool to label this issue as bug/feature/question: '…'."* or
   *"Use the engine's `compose_and_run` to summarize this text: …"*. Claude Desktop's model calls the tool; the engine
   runs the specialist/workflow and returns the result.

Note: this is the *tool-calling* path, which Claude Desktop and other clients support broadly. (The old
"sampling / brainless server" idea — the engine borrowing the caller's model — was removed: the 2026-07-28 MCP
spec deprecated sampling and no mainstream client implements it.)

## Demo + tests

- **Demo:** `python examples/scripts/mcp_demo.py` — runs both directions, brain-free (skips if `mcp` absent):
  IMPORT (a real `mcp_call` recipe step pulls from a mock MCP server through the dispatcher) and EXPORT
  (an MCP client discovers all 16 engine tools and calls one). The four use cases above go further with real
  data.
- **Tests:** `tests/test_mcp.py` — real end-to-end over stdio (the protocol is not mocked): the `mcp_call`
  specialist against a mock server (`tests/mcp_mock_server.py`), and an MCP client discovering + calling
  the engine's exported tools. Both **skip cleanly** if `mcp` isn't installed, so the core-only suite stays
  green. Wired into `tests/run_all.py`.

## The honest cost

Net-positive but not free — the PR should say so:
- **A new dependency** (`mcp` + transitive deps), even as an optional extra.
- **Maintenance**: MCP is a young, evolving spec (transports, auth, tool schemas); the adapters need
  upkeep. (One example already: FastMCP doesn't emit structured content for a bare `dict` return, so the
  client `_unwrap` also parses JSON text — the kind of small compatibility handling this surface accrues.)
- **Surface area** + **edge fragility** (stdio handshakes, subprocess launches, timeouts) — mitigated with
  a per-call timeout, not eliminated.

Kept contained by staying optional, lazy, and strictly at the edges — but real, so "no downsides" would be
the wrong way to sell it.
