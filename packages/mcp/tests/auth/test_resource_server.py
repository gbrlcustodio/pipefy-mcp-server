"""Unit tests for the resource-server adapter: claims -> AccessToken, reject -> None.

The JWT/JWKS validation itself is covered in ``pipefy_auth``'s
``test_verification.py``. These tests use a stub validator to pin the adapter's
two jobs: mapping validated claims onto the SDK ``AccessToken`` and turning a
validation failure into ``None`` (which FastMCP renders as a 401).
"""

from __future__ import annotations

from typing import Any

import pytest
from pipefy_auth import TokenValidationError

from pipefy_mcp.auth import JwtTokenVerifier

_AUDIENCE = "https://mcp.example.com/mcp"


class _StubValidator:
    def __init__(self, *, claims: dict[str, Any] | None = None, raises: bool = False):
        self._claims = claims or {}
        self._raises = raises
        self.audience = _AUDIENCE

    def validate(self, token: str) -> dict[str, Any]:
        if self._raises:
            raise TokenValidationError("bad token")
        return self._claims


@pytest.mark.unit
async def test_maps_claims_to_access_token() -> None:
    validator = _StubValidator(
        claims={
            "azp": "client-abc",
            "sub": "user-123",
            "scope": "read write",
            "exp": 1893456000,
        }
    )
    token = await JwtTokenVerifier(validator).verify_token("the-token")
    assert token is not None
    assert token.token == "the-token"
    assert token.client_id == "client-abc"
    assert token.scopes == ["read", "write"]
    assert token.expires_at == 1893456000
    assert token.resource == _AUDIENCE


@pytest.mark.unit
async def test_client_id_falls_back_to_client_id_then_sub() -> None:
    by_client_id = await JwtTokenVerifier(
        _StubValidator(claims={"client_id": "cid", "sub": "user-123"})
    ).verify_token("t")
    assert by_client_id is not None and by_client_id.client_id == "cid"

    by_sub = await JwtTokenVerifier(
        _StubValidator(claims={"sub": "user-123"})
    ).verify_token("t")
    assert by_sub is not None and by_sub.client_id == "user-123"


@pytest.mark.unit
async def test_missing_scope_claim_yields_empty_scopes() -> None:
    token = await JwtTokenVerifier(
        _StubValidator(claims={"sub": "user-123"})
    ).verify_token("t")
    assert token is not None and token.scopes == []


@pytest.mark.unit
async def test_validation_failure_returns_none() -> None:
    token = await JwtTokenVerifier(_StubValidator(raises=True)).verify_token("t")
    assert token is None
