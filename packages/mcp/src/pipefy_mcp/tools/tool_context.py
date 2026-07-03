"""Resolve request-scoped resources from the MCP lifespan context."""

from __future__ import annotations

from mcp.server.fastmcp import Context
from pipefy_sdk import PipefyClient

from pipefy_mcp.core.runtime import McpRuntime


def get_pipefy_client(ctx: Context) -> PipefyClient:
    """Return a Pipefy client session bound to the in-flight request's identity.

    The server builds the app-scoped :class:`McpRuntime` at startup and its
    lifespan yields it as the request ``lifespan_context``. The runtime owns the
    shared engine and opens a cheap session here, per call, bound to the caller's
    identity (see :meth:`McpRuntime.session_for_request`). Resolving per call, not
    at registration, is what keeps identity request-scoped: under the hosted
    profile the session carries this request's validated bearer, read off the
    message's own ``request_context.request`` and passed in, so concurrent callers
    each act as themselves without re-registering the tool table.
    """
    request_context = ctx.request_context
    runtime: McpRuntime = request_context.lifespan_context
    return runtime.session_for_request(request_context.request)
