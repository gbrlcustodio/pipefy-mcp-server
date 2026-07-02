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
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator

from httpx import Auth, Request, Response
from mcp.server.auth.middleware.auth_context import get_access_token


def require_request_bearer() -> str:
    """Return the validated bearer token for the in-flight MCP request.

    FastMCP's ``AuthContextMiddleware`` stores the ``AccessToken`` it validated
    in a per-request contextvar; this reads it back. Raises when no token is
    present (a call ran outside the resource-server request scope), so a missing
    identity fails loudly instead of issuing an unauthenticated Pipefy call.
    """
    access = get_access_token()
    if access is None or not access.token:
        raise RuntimeError(
            "No authenticated access token in the request context; the "
            "resource-server profile must validate a bearer before a tool runs."
        )
    return access.token


class RequestContextBearerAuth(Auth):
    """Attach ``Authorization: Bearer …`` from the request's validated token.

    Stateless by design: the token is read from the request contextvar inside
    the auth flow, which httpx runs in the calling request's task/context, so a
    single shared instance carries no identity between requests. That is what
    lets one app-scoped client serve every concurrent caller as themselves under
    a multi-worker deployment, with no chance of one request's bearer
    authenticating another's call.

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
