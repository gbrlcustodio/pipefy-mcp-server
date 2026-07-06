"""Resolve request-scoped resources from the MCP lifespan context."""

from __future__ import annotations

from mcp.server.fastmcp import Context
from pipefy_sdk import PipefyClient

from pipefy_mcp.core.runtime import McpRuntime


def get_pipefy_client(ctx: Context) -> PipefyClient:
    """Return the live Pipefy client for the in-flight request.

    The server builds the app-scoped :class:`McpRuntime` at startup and its
    lifespan yields it as the request ``lifespan_context``. The runtime wires its
    shared client at construction, so it always holds one. Tools read the client
    from it per call rather than closing over one at registration. The client is
    shared; under the hosted profile it applies the request's own identity via
    its httpx auth, so reading it per call (not per registration) is what keeps
    identity request-scoped without re-registering the tool table.
    """
    runtime: McpRuntime = ctx.request_context.lifespan_context
    return runtime.pipefy_client
