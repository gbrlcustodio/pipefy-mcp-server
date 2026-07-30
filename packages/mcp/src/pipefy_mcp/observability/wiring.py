"""Wire hosted observability into the Streamable HTTP Starlette app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.applications import Starlette

from pipefy_mcp.observability.request_log_middleware import RequestLogMiddleware

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer
    from mcp.server.transport_security import TransportSecuritySettings


def wire_hosted_observability(
    app: MCPServer,
    *,
    host: str = "127.0.0.1",
    transport_security: TransportSecuritySettings | None = None,
    json_response: bool = False,
) -> Starlette:
    """Build the HTTP app once and attach hosted observability.

    ``streamable_http_app()`` must run exactly once: each call builds a new
    Starlette app (only the session manager is cached), so calling it again after
    wiring would drop the middleware.

    ``host`` and ``transport_security`` are per-transport SDK arguments, so they
    arrive here rather than on the ``MCPServer`` constructor. ``host`` seeds the
    SDK's own allowlist default, and ``transport_security`` replaces it when the
    deployment configured one. Leaving both at their defaults keeps the SDK's
    loopback-only posture, which is what a local subprocess install wants.

    ``json_response`` is forwarded for the same reason: 2.0 moved it off the server
    settings onto this call. The serving path leaves it off, so a POST reply is
    SSE-framed as before; the observability tests set it to read a reply as plain
    JSON without an SSE parser.
    """
    http_app = app.streamable_http_app(
        host=host,
        transport_security=transport_security,
        json_response=json_response,
    )
    http_app.add_middleware(RequestLogMiddleware)
    return http_app
