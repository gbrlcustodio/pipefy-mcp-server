"""Wire hosted observability into the Streamable HTTP Starlette app."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette

from pipefy_mcp.observability.request_log_middleware import RequestLogMiddleware


def wire_hosted_observability(app: MCPServer) -> Starlette:
    """Build the HTTP app once and attach hosted observability.

    ``streamable_http_app()`` must run exactly once: each call builds a new
    Starlette app (only the session manager is cached), so calling it again after
    wiring would drop the middleware.
    """
    http_app = app.streamable_http_app()
    http_app.add_middleware(RequestLogMiddleware)
    return http_app
