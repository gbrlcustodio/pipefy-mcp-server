"""Unit tests for reading the request-scoped bearer (hosted profile).

``require_request_bearer`` reads the validated token FastMCP stored in the
request contextvar. The per-session snapshot and cross-caller isolation now live
on the runtime (:class:`RequestScopedIdentity`), tested in
``tests/core/test_runtime.py``; here we pin the contextvar read and its
raise-on-missing contract.
"""

from __future__ import annotations

import pytest
from mcp.server.auth.middleware.auth_context import (
    AuthenticatedUser,
    auth_context_var,
)
from mcp.server.auth.provider import AccessToken

from pipefy_mcp.auth.request_identity import require_request_bearer


def _authenticated(token: str) -> AuthenticatedUser:
    return AuthenticatedUser(AccessToken(token=token, client_id=token, scopes=[]))


@pytest.mark.unit
def test_reads_the_validated_request_token():
    """Returns the token FastMCP validated for the in-flight request."""
    handle = auth_context_var.set(_authenticated("req-token"))
    try:
        assert require_request_bearer() == "req-token"
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
