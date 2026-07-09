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

from dataclasses import dataclass, field

from mcp.server.auth.middleware.auth_context import AuthenticatedUser
from starlette.requests import Request


@dataclass(frozen=True)
class CallerIdentity:
    """The validated caller a tool-call middleware acts on behalf of.

    Sourced from the request's validated bearer, never re-decoded. ``client_id``
    is the OAuth client (``azp``/``client_id``, falling back to ``sub`` for a
    user token) and ``scopes`` its granted scopes. Both default empty: under the
    stdio/local profile there is no inbound bearer, so middleware sees an
    anonymous identity rather than a failure.

    The end-user subject is intentionally deferred: its consumer (per-user
    quotas) is not built yet. Both profiles can source it when it lands, the
    remote profile from the validated ``sub`` claim and the local profile from
    the configured JWT credential.
    """

    client_id: str | None = None
    scopes: tuple[str, ...] = field(default_factory=tuple)


def _authenticated_user(request: Request | None) -> AuthenticatedUser | None:
    """Return the RS-validated user off the request, or None.

    Reads ``request.scope`` directly rather than ``request.user``: the latter
    asserts ``AuthenticationMiddleware`` is installed, which holds only under the
    ``remote`` profile, so touching the property would raise on a ``local`` HTTP
    request. This is the one place both request-scoped readers agree on how the
    validated caller is located: off the per-message request, never
    ``auth_context_var``.
    """
    user = request.scope.get("user") if request is not None else None
    return user if isinstance(user, AuthenticatedUser) else None


def caller_identity(request: Request | None) -> CallerIdentity:
    """Return the validated caller off the in-flight request, or an anonymous one.

    Runs on every profile (a tool-call middleware wraps both transports), so a
    missing or non-authenticated user yields the empty :class:`CallerIdentity`
    rather than an error.
    """
    user = _authenticated_user(request)
    if user is None:
        return CallerIdentity()
    token = user.access_token
    return CallerIdentity(client_id=token.client_id, scopes=tuple(token.scopes))


def require_request_bearer(request: Request | None) -> str:
    """Return the validated bearer token off the in-flight request.

    The resource-server middleware sets the validated ``AuthenticatedUser`` on
    the request; this reads its access token. Taking the
    request as an argument (the runtime passes ``ctx.request_context.request`` from
    the tool handler) keeps the read on the current caller: it never touches
    ``auth_context_var``, which stateful Streamable HTTP freezes at the session's
    first bearer.

    Raises when no validated bearer is present (called outside the resource-server
    request scope, or the request bore no ``AuthenticatedUser``), so a missing
    identity fails loudly instead of issuing an unauthenticated Pipefy call.
    """
    user = _authenticated_user(request)
    if user is None or not user.access_token.token:
        raise RuntimeError(
            "No authenticated access token on the request. Under the "
            "resource-server profile this means either the caller sent no valid "
            "bearer or the authentication middleware is not wired into the ASGI "
            "stack; a tool must not run without a validated caller."
        )
    return user.access_token.token
