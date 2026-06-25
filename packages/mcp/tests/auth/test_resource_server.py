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
    token = await JwtTokenVerifier(validator, resource=_AUDIENCE).verify_token(
        "the-token"
    )
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
async def test_scope_claim_as_list_maps_to_scopes() -> None:
    # RFC 9068 specifies a space-delimited string, but some IdPs emit an array;
    # it must map rather than crash (a list has no .split()).
    token = await JwtTokenVerifier(
        _StubValidator(claims={"sub": "user-123", "scope": ["read", "write"]})
    ).verify_token("t")
    assert token is not None and token.scopes == ["read", "write"]


@pytest.mark.unit
async def test_fractional_exp_is_coerced_to_int() -> None:
    # exp is an RFC 7519 NumericDate and may be fractional; AccessToken wants an
    # int, so it is truncated rather than crashing the mapping.
    token = await JwtTokenVerifier(
        _StubValidator(claims={"sub": "user-123", "exp": 1893456000.5})
    ).verify_token("t")
    assert token is not None and token.expires_at == 1893456000


@pytest.mark.unit
async def test_unmappable_claims_return_none() -> None:
    # A validly-signed token whose claims can't map onto an AccessToken is a
    # rejection (None -> 401), never an escaping exception (500).
    token = await JwtTokenVerifier(
        _StubValidator(claims={"sub": "user-123", "exp": "not-a-number"})
    ).verify_token("t")
    assert token is None


@pytest.mark.unit
async def test_validation_failure_returns_none() -> None:
    token = await JwtTokenVerifier(_StubValidator(raises=True)).verify_token("t")
    assert token is None
