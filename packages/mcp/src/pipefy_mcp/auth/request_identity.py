"""Request-scoped identity for the hosted resource-server profile.

The HTTP resource-server profile validates an inbound bearer on every request
(see :mod:`pipefy_mcp.auth.resource_server`) and the shared Pipefy client acts on
behalf of that caller rather than as one identity resolved at startup. This
module bridges the two: it reads the request's validated bearer and adapts it to
the ``httpx.Auth`` the shared client applies to each outbound call.

The adapter is the on-behalf-of counterpart to the credential-backed adapters in
:mod:`pipefy_auth.bearer` (which resolve a single startup identity). It is
stateless so one shared instance can serve every concurrent caller as
themselves; see :class:`RequestContextBearerAuth` for the isolation rationale.

The bearer is read from the per-message request context, not from
``AuthContextMiddleware``'s ``auth_context_var``. Under stateful Streamable HTTP
the tool handler runs inside a long-lived per-session task whose captured
``auth_context_var`` is frozen at session ``initialize`` time, so it would replay
the session initializer's bearer on every later call. The low-level server sets
``request_ctx`` afresh for each JSON-RPC message, carrying that message's own
validated request, so it is the source that tracks the current caller.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator

from httpx import Auth, Request, Response
from mcp.server.auth.provider import AccessToken
from mcp.server.lowlevel.server import request_ctx


def _get_access_token() -> AccessToken | None:
    """Return the validated access token for the in-flight MCP message, or None.

    The per-message counterpart to
    :func:`mcp.server.auth.middleware.auth_context.get_access_token`, which this
    replaces: it reads the token off the current message's request context
    (``request.user.access_token``, which the low-level server sets per JSON-RPC
    message from that message's own HTTP request) rather than the session task's
    ``auth_context_var``, which stateful Streamable HTTP freezes at ``initialize``.
    Returns None outside a request scope, or when the request bears no validated
    user, mirroring the SDK helper's ``AccessToken | None`` contract.
    """
    try:
        ctx = request_ctx.get()
    except LookupError:
        return None
    user = getattr(ctx.request, "user", None)
    return getattr(user, "access_token", None)


def require_request_bearer() -> str:
    """Return the validated bearer token for the in-flight MCP message.

    Raises when no authenticated token is present (a call ran outside the
    resource-server request scope, or the request bore no validated bearer), so a
    missing identity fails loudly instead of issuing an unauthenticated Pipefy call.
    """
    access = _get_access_token()
    if access is None or not access.token:
        raise RuntimeError(
            "No authenticated access token in the request context; the "
            "resource-server profile must validate a bearer before a tool runs."
        )
    return access.token


class RequestContextBearerAuth(Auth):
    """Attach ``Authorization: Bearer …`` from the current message's validated token.

    Stateless by design: the token is read from the per-message ``request_ctx``
    (see :func:`require_request_bearer`) inside the auth flow, so a single shared
    instance carries no identity between requests. That is what lets one
    app-scoped client serve every concurrent caller as themselves under a
    multi-worker deployment, with no chance of one request's bearer
    authenticating another's call, and it tracks mid-session token refresh
    because it re-reads the source each call rather than a session-init snapshot.

    It deliberately takes no lock and no thread hop: reading the contextvar is
    cheap and synchronous, so there is nothing to serialize. A keychain-refresh
    adapter must funnel its blocking refresh through one critical section; doing
    the same here would put every user's outbound call through one process-wide
    lock for no reason.
    """

    def auth_flow(self, request: Request) -> Generator[Request, Response, None]:
        request.headers["Authorization"] = f"Bearer {require_request_bearer()}"
        yield request

    async def async_auth_flow(
        self, request: Request
    ) -> AsyncGenerator[Request, Response]:
        request.headers["Authorization"] = f"Bearer {require_request_bearer()}"
        yield request
