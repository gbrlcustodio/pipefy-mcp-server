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
from _rs_fixtures import authenticated_user, request_with_user
from mcp.server.auth.middleware.auth_context import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from starlette.requests import Request

from pipefy_mcp.auth.request_identity import (
    CallerIdentity,
    caller_identity,
    require_request_bearer,
)


@pytest.mark.unit
def test_reads_the_validated_request_token():
    """Returns the token the resource server validated for the in-flight request."""
    request = request_with_user(authenticated_user("req-token"))
    assert require_request_bearer(request) == "req-token"


@pytest.mark.unit
def test_raises_without_a_request():
    """A call with no request (outside the resource-server scope) fails loudly."""
    with pytest.raises(RuntimeError, match="No authenticated access token"):
        require_request_bearer(None)


@pytest.mark.unit
def test_raises_without_a_validated_user():
    """A request with no authenticated user fails loudly."""
    with pytest.raises(RuntimeError, match="No authenticated access token"):
        require_request_bearer(request_with_user(None))


@pytest.mark.unit
def test_raises_on_empty_token():
    """An access token with an empty string is treated as absent."""
    with pytest.raises(RuntimeError, match="No authenticated access token"):
        require_request_bearer(request_with_user(authenticated_user("")))


@pytest.mark.unit
def test_caller_identity_reads_client_id_and_scopes():
    """The validated caller's client id and scopes come off the request's token."""
    user = AuthenticatedUser(
        AccessToken(token="t", client_id="acting-client", scopes=["read", "write"])
    )
    identity = caller_identity(request_with_user(user))
    assert identity == CallerIdentity(
        client_id="acting-client", scopes=("read", "write")
    )


@pytest.mark.unit
def test_caller_identity_is_anonymous_without_a_request():
    """No request (stdio, or outside the request scope) yields the empty identity."""
    assert caller_identity(None) == CallerIdentity()


@pytest.mark.unit
def test_caller_identity_is_anonymous_without_a_validated_user():
    """A request whose user is not authenticated yields the empty identity."""
    assert caller_identity(request_with_user(None)) == CallerIdentity()


@pytest.mark.unit
def test_caller_identity_survives_a_scope_without_a_user_key():
    """A local-over-HTTP request has no ``user`` in scope; reading it must not raise.

    ``AuthenticationMiddleware`` runs only under the remote profile, so a
    ``local`` HTTP request never gets a ``user`` scope key. ``request.user`` would
    assert; ``caller_identity`` reads ``scope`` directly and returns anonymous.
    """
    request = Request({"type": "http", "headers": []})
    assert caller_identity(request) == CallerIdentity()
