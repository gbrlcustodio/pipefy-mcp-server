"""Unit tests for reading the request-scoped bearer (hosted profile).

``require_request_bearer`` reads the validated token off the request the tool
handler passes in (``request.user.access_token``), not a contextvar, so it tracks
the current caller even under stateful Streamable HTTP. The per-session snapshot
and cross-caller isolation live on the runtime (:class:`RequestScopedIdentity`),
tested in ``tests/core/test_runtime.py``; here we pin the read off the request and
its raise-on-missing contract.
"""

from __future__ import annotations

import pytest
from mcp.server.auth.middleware.auth_context import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from starlette.requests import Request

from pipefy_mcp.auth.request_identity import require_request_bearer


def _authenticated(token: str) -> AuthenticatedUser:
    return AuthenticatedUser(AccessToken(token=token, client_id=token, scopes=[]))


def _request(user: AuthenticatedUser | None) -> Request:
    """A Starlette request whose ``scope["user"]`` is what the RS validated.

    Mirrors what the resource-server middleware leaves on each message's request:
    an ``AuthenticatedUser`` when a bearer validated, or ``None`` otherwise.
    """
    return Request({"type": "http", "headers": [], "user": user})


@pytest.mark.unit
def test_reads_the_validated_request_token():
    """Returns the token the resource server validated for the in-flight request."""
    assert require_request_bearer(_request(_authenticated("req-token"))) == "req-token"


@pytest.mark.unit
def test_raises_without_a_request():
    """A call with no request (outside the resource-server scope) fails loudly."""
    with pytest.raises(RuntimeError, match="No authenticated access token"):
        require_request_bearer(None)


@pytest.mark.unit
def test_raises_without_a_validated_user():
    """A request with no authenticated user fails loudly."""
    with pytest.raises(RuntimeError, match="No authenticated access token"):
        require_request_bearer(_request(None))


@pytest.mark.unit
def test_raises_on_empty_token():
    """An access token with an empty string is treated as absent."""
    with pytest.raises(RuntimeError, match="No authenticated access token"):
        require_request_bearer(_request(_authenticated("")))
