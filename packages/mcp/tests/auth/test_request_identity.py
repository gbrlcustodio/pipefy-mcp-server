"""Unit tests for the request-scoped identity bridge (hosted profile).

The isolation test is the on-behalf-of acceptance criterion: one shared
:class:`RequestContextBearerAuth` instance, driven concurrently by many tasks
that each carry a different validated token, must attach each task's own token
and never another's. This is what lets a single app-scoped client serve every
caller as themselves under a multi-worker deployment.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from mcp.server.auth.middleware.auth_context import (
    AuthenticatedUser,
    auth_context_var,
)
from mcp.server.auth.provider import AccessToken

from pipefy_mcp.auth.request_identity import (
    RequestContextBearerAuth,
    require_request_bearer,
)


def _authenticated(token: str) -> AuthenticatedUser:
    return AuthenticatedUser(AccessToken(token=token, client_id=token, scopes=[]))


async def _bearer_seen(auth: RequestContextBearerAuth, token: str) -> str:
    """Set ``token`` as the request identity, run the auth flow, return the header.

    Sets and resets the contextvar so a caller in its own task observes only its
    own token; an ``await`` between set and read forces tasks to interleave, so
    any shared per-request state on ``auth`` would surface as a cross-token leak.
    """
    handle = auth_context_var.set(_authenticated(token))
    try:
        await asyncio.sleep(0)
        request = httpx.Request("POST", "https://api.pipefy.test/graphql")
        async for prepared in auth.async_auth_flow(request):
            return prepared.headers["Authorization"]
        raise AssertionError("auth flow yielded no request")
    finally:
        auth_context_var.reset(handle)


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
def test_sync_auth_flow_reads_the_request_token():
    """The sync flow reads the contextvar inline too (parity with the async path)."""
    auth = RequestContextBearerAuth()
    handle = auth_context_var.set(_authenticated("sync-token"))
    try:
        request = httpx.Request("POST", "https://api.pipefy.test/graphql")
        prepared = next(auth.auth_flow(request))
        assert prepared.headers["Authorization"] == "Bearer sync-token"
    finally:
        auth_context_var.reset(handle)


@pytest.mark.unit
def test_require_request_bearer_raises_without_a_validated_token():
    """A call outside the resource-server request scope fails loudly."""
    with pytest.raises(RuntimeError, match="No authenticated access token"):
        require_request_bearer()


@pytest.mark.unit
def test_require_request_bearer_raises_on_empty_token():
    """An access token with an empty string is treated as absent."""
    handle = auth_context_var.set(_authenticated(""))
    try:
        with pytest.raises(RuntimeError, match="No authenticated access token"):
            require_request_bearer()
    finally:
        auth_context_var.reset(handle)
