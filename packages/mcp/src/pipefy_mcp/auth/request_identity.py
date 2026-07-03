"""Request-scoped identity for the hosted resource-server profile.

The HTTP resource-server profile validates an inbound bearer on every request
(see :mod:`pipefy_mcp.auth.resource_server`) and the server acts on behalf of
that caller rather than as one identity resolved at startup. This module reads
the caller's validated bearer off the request the tool handler received, so the
runtime can snapshot it into a per-session credential (see
:meth:`pipefy_mcp.core.runtime.RequestScopedIdentity.resolve`).

The bearer comes from the request the handler passes in
(``ctx.request_context.request``), not from ``AuthContextMiddleware``'s
``auth_context_var``. Under stateful Streamable HTTP the runtime resolves identity
from the tool handler, which runs in a long-lived per-session task whose captured
``auth_context_var`` is frozen at session ``initialize``; the request the low-level
server threads onto ``request_context`` is per-message, so it tracks the current
caller.
"""

from __future__ import annotations


def require_request_bearer(request: object | None) -> str:
    """Return the validated bearer token off the in-flight request.

    The resource-server middleware sets ``request.user`` to the
    ``AuthenticatedUser`` it validated; this reads its access token. Taking the
    request as an argument (the runtime passes ``ctx.request_context.request`` from
    the tool handler) keeps the read on the current caller: it never touches
    ``auth_context_var``, which stateful Streamable HTTP freezes at the session's
    first bearer.

    Raises when no validated bearer is present (called outside the resource-server
    request scope, or the request bore no authenticated user), so a missing
    identity fails loudly instead of issuing an unauthenticated Pipefy call.
    """
    user = getattr(request, "user", None)
    access = getattr(user, "access_token", None)
    if access is None or not access.token:
        raise RuntimeError(
            "No authenticated access token on the request; the resource-server "
            "profile must validate a bearer before a tool runs."
        )
    return access.token
