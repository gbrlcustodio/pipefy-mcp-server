"""Resolve request-scoped resources from the MCP lifespan context."""

from __future__ import annotations

from mcp.server.fastmcp import Context
from pipefy_sdk import PipefyClient

from pipefy_mcp.core.container import ServicesContainer


def get_pipefy_client(ctx: Context) -> PipefyClient:
    """Return the live Pipefy client for the in-flight request.

    The server lifespan initializes services and yields the
    :class:`ServicesContainer` as the request ``lifespan_context``. Tools read the
    client from it per call rather than closing over one at registration, so a
    request-scoped identity (issue #302) can vary the client without
    re-registering the tool table.
    """
    container: ServicesContainer = ctx.request_context.lifespan_context
    client = container.pipefy_client
    if client is None:
        raise RuntimeError(
            "Pipefy client is not initialized; the server lifespan must "
            "initialize services before any tool is invoked."
        )
    return client
