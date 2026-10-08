# Examples

The runs and compositions here are real — real input, the engine's real output, nothing edited.
A few `scripts/` are deliberately synthetic so they can prove one mechanism in isolation; those say so.

| folder | what's in it |
|---|---|
| [`full_run/`](full_run/) | complete runs: a recipe on real input → the run log + what it produced (`output/`) |
| [`composer/`](composer/) | the Composer's work: a plain-English task → the workflow it built |
| [`scripts/`](scripts/) | runnable one-liners — `python examples/scripts/<name>.py` |
| [`mcp_servers/`](mcp_servers/) | two tiny MCP servers (GitHub issues, Hacker News) over public APIs, so the MCP demos need no secrets |

**MCP interop** (`docs/mcp.md`) — the engine consumes MCP tools and exposes its specialists as MCP tools:

| script | what it shows |
|---|---|
| `mcp_demo.py` | brain-free: an `mcp_call` step pulls from a mock server, and a client lists + calls the engine's exported tools |
| `mcp_github_triage.py` | real data: live GitHub issues via an external MCP server → classify + route + summarize each |
| `mcp_symmetry.py` | real data: the same Hacker News stories via native `fetch` vs an MCP tool → identical shape, identical downstream |
| `mcp_server_and_client.py` | real data: the engine as MCP server *and* client at once (our client → engine → the official filesystem server) |

Driving the engine from Claude Desktop is a ~2-minute manual setup, also in `docs/mcp.md`.

**Run your own** (see the [README](../README.md#do-it-yourself)):
```bash
python -m engine.cli run triage --repo <any/public-repo> --limit 5
python -m engine.cli compose "<describe a job in plain English>"
```
