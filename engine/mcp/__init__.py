"""MCP interop for the engine — EDGE ONLY, and symmetric.

An engine specialist and an MCP tool are the same shape of thing: a named capability with typed inputs
and outputs. So the engine speaks the Model Context Protocol in both directions by mapping between the two:

  - IMPORT (client) : the `mcp_call` specialist adopts any external MCP tool as an engine capability.
  - EXPORT (server) : `engine.mcp.server` publishes each engine specialist as an MCP tool.

Hard rule: this is an adapter/entry-point layer. It imports FROM the core; the core never imports it.
The `mcp` SDK is an OPTIONAL dependency (`pip install -e '.[mcp]'`), lazy-imported inside functions, so
a core install and every non-MCP workflow run without it ever loading.
"""
