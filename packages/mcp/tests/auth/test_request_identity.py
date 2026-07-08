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

from pipefy_mcp.auth.request_identity import require_request_bearer


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
