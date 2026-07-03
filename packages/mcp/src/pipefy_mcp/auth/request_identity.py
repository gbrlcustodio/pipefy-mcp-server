"""Request-scoped identity for the hosted resource-server profile.

The HTTP resource-server profile validates an inbound bearer on every request
(see :mod:`pipefy_mcp.auth.resource_server`) and the server acts on behalf of
that caller rather than as one identity resolved at startup. This module reads
the request's validated bearer back out of the request context so the runtime can
snapshot it into a per-session credential (see
:meth:`pipefy_mcp.core.runtime.RequestScopedIdentity.resolve`).
"""

from __future__ import annotations

from mcp.server.auth.middleware.auth_context import get_access_token


def require_request_bearer() -> str:
    """Return the validated bearer token for the in-flight MCP request.

    FastMCP's ``AuthContextMiddleware`` stores the ``AccessToken`` it validated
    in a per-request contextvar; this reads it back. Raises when no token is
    present (a call ran outside the resource-server request scope), so a missing
    identity fails loudly instead of issuing an unauthenticated Pipefy call.

    Read this in the caller's task, where the contextvar is set: the runtime calls
    it inside :meth:`RequestScopedIdentity.resolve` when opening the request's
    session, so the token is snapshotted per request rather than shared.
    """
    access = get_access_token()
    if access is None or not access.token:
        raise RuntimeError(
            "No authenticated access token in the request context; the "
            "resource-server profile must validate a bearer before a tool runs."
        )
    return access.token
