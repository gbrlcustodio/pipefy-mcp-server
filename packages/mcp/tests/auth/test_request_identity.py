"""Unit tests for the request-scoped identity bridge (hosted profile).

The isolation test is the on-behalf-of acceptance criterion: one shared
:class:`RequestContextBearerAuth` instance, driven concurrently by many tasks
that each carry a different validated token, must attach each task's own token
and never another's. This is what lets a single app-scoped client serve every
caller as themselves under a multi-worker deployment.

The stateful-topology test is the transport-level acceptance criterion: the
adapter must read each MCP message's own bearer, not the one captured when the
session's server task was spawned at ``initialize``. See the module docstring of
:mod:`pipefy_mcp.auth.request_identity` for why the two diverge under stateful
Streamable HTTP.
"""

from __future__ import annotations

import asyncio

import anyio
import httpx
import pytest
from mcp.server.auth.middleware.auth_context import (
    AuthenticatedUser,
    auth_context_var,
)
from mcp.server.auth.provider import AccessToken
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from starlette.requests import Request

from pipefy_mcp.auth.request_identity import (
    RequestContextBearerAuth,
    require_request_bearer,
)


def _authenticated(token: str) -> AuthenticatedUser:
    return AuthenticatedUser(AccessToken(token=token, client_id=token, scopes=[]))


def _request_context(user: AuthenticatedUser | None) -> RequestContext:
    """A per-message request context whose Starlette request carries ``user``.

    Mirrors what the low-level server builds per JSON-RPC message: the message's
    own Starlette ``Request``, with ``scope["user"]`` set to whatever the resource
    server validated for that request (an ``AuthenticatedUser``, or ``None`` when
    the request bore no validated user).
    """
    scope = {"type": "http", "headers": [], "user": user}
    return RequestContext(
        request_id=1,
        meta=None,
        session=None,  # type: ignore[arg-type]  # unused by the adapter
        lifespan_context=None,
        request=Request(scope),
    )


def _message_context(token: str) -> RequestContext:
    """A per-message request context whose validated request carries ``token``."""
    return _request_context(_authenticated(token))


async def _bearer_seen(auth: RequestContextBearerAuth, token: str) -> str:
    """Set ``token`` as the message identity, run the auth flow, return the header.

    Sets and resets the contextvar so a caller in its own task observes only its
    own token; an ``await`` between set and read forces tasks to interleave, so
    any shared per-request state on ``auth`` would surface as a cross-token leak.
    """
    handle = request_ctx.set(_message_context(token))
    try:
        await asyncio.sleep(0)
        request = httpx.Request("POST", "https://api.pipefy.test/graphql")
        async for prepared in auth.async_auth_flow(request):
            return prepared.headers["Authorization"]
        raise AssertionError("auth flow yielded no request")
    finally:
        request_ctx.reset(handle)


@pytest.mark.unit
async def test_concurrent_callers_each_get_their_own_token():
    """A shared instance under fan-out attaches each task's own token, only its own."""
    auth = RequestContextBearerAuth()
    tokens = [f"user-{i}-token" for i in range(24)]

    headers = await asyncio.gather(*(_bearer_seen(auth, t) for t in tokens))

    assert headers == [f"Bearer {t}" for t in tokens]


@pytest.mark.unit
async def test_same_instance_reads_a_fresh_token_each_request():
    """No cached identity: the one instance reflects the current request's token."""
    auth = RequestContextBearerAuth()

    first = await _bearer_seen(auth, "token-A")
    second = await _bearer_seen(auth, "token-B")

    assert first == "Bearer token-A"
    assert second == "Bearer token-B"


@pytest.mark.unit
async def test_stateful_session_task_reads_current_message_bearer():
    """Reproduces stateful Streamable HTTP: the frozen session bearer must not win.

    Under stateful mode the per-session server task is spawned inside the
    ``initialize`` request (bearer A) and captures its ``auth_context_var``; later
    ``tools/call`` messages run in that same task but carry their own request
    (bearer B) via ``request_ctx``. The adapter must attach B, the current caller.

    Reading the session-frozen ``get_access_token()`` instead would attach
    ``Bearer token-A`` here; the same-task unit tests above cannot catch that
    because they never span the two-task topology this reproduces.
    """
    auth = RequestContextBearerAuth()
    seen: list[str] = []

    async def session_server_task() -> None:
        # This task captured auth_context_var == "token-A" at spawn (the frozen
        # session-init bearer). A later tools/call message sets request_ctx to its
        # own request (bearer B) for the duration of the handler.
        handle = request_ctx.set(_message_context("token-B"))
        try:
            outbound = httpx.Request("POST", "https://api.pipefy.test/graphql")
            async for prepared in auth.async_auth_flow(outbound):
                seen.append(prepared.headers["Authorization"])
                break
        finally:
            request_ctx.reset(handle)

    # The session-init ASGI task: auth_context_var is set to A here, and the server
    # task is spawned within this context so it captures A, frozen for the session.
    auth_context_var.set(_authenticated("token-A"))
    async with anyio.create_task_group() as tg:
        tg.start_soon(session_server_task)

    assert seen == ["Bearer token-B"]


@pytest.mark.unit
def test_sync_auth_flow_reads_the_request_token():
    """The sync flow reads the request context inline too (parity with async)."""
    auth = RequestContextBearerAuth()
    handle = request_ctx.set(_message_context("sync-token"))
    try:
        request = httpx.Request("POST", "https://api.pipefy.test/graphql")
        prepared = next(auth.auth_flow(request))
        assert prepared.headers["Authorization"] == "Bearer sync-token"
    finally:
        request_ctx.reset(handle)


@pytest.mark.unit
def test_require_request_bearer_raises_without_a_request_context():
    """A call outside any MCP request scope fails loudly."""
    with pytest.raises(RuntimeError, match="No authenticated access token"):
        require_request_bearer()


@pytest.mark.unit
def test_require_request_bearer_raises_without_a_validated_user():
    """A request context with no authenticated user fails loudly."""
    handle = request_ctx.set(_request_context(None))
    try:
        with pytest.raises(RuntimeError, match="No authenticated access token"):
            require_request_bearer()
    finally:
        request_ctx.reset(handle)


@pytest.mark.unit
def test_require_request_bearer_raises_on_empty_token():
    """An access token with an empty string is treated as absent."""
    handle = request_ctx.set(_message_context(""))
    try:
        with pytest.raises(RuntimeError, match="No authenticated access token"):
            require_request_bearer()
    finally:
        request_ctx.reset(handle)
