"""mcp_call — capability specialist: call a tool on any external MCP server.

The IMPORT half of the engine's MCP symmetry: it adopts an external MCP tool as an engine capability, so a
recipe step can use any tool exposed by any MCP server and get its result back. Pure plumbing (no brain,
no golds) — an I/O adapter like `fetch` and `act`. The `mcp` SDK is imported lazily by the client
adapter, so this specialist registers fine without the optional dependency and only needs it at run time.
"""

from __future__ import annotations

from ..core import Contract, Specialist


class McpCall(Specialist):
    name = "mcp_call"
    kind = "capability"
    description = (
        "Call a named tool on any external MCP (Model Context Protocol) server and return its result. "
        "USE WHEN a recipe needs a capability provided by an external MCP server (a company tool, a data "
        "service, another agent). "
        "NOT for pulling a list of items from a built-in source (->fetch), staging a local side-effect "
        "(->act), or any judgment (->classify/rank/verify). "
        "CONFIG-DRIVEN via {server (how to launch it), tool, arguments} -- reuse for any MCP tool, don't "
        "clone. IN server,tool,arguments -> OUT result."
    )
    contract = Contract(
        input={"server": dict, "tool": str, "arguments": dict},
        output={"result": object},
    )

    def _run(self, input, config):
        from ..mcp.client import call_tool     # lazy: pulls the optional mcp SDK only when actually run
        result = call_tool(input["server"], input["tool"], input.get("arguments", {}))
        return {"result": result}
