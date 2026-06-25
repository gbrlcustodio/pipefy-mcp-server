"""Unit tests for the resource-server adapter and its composition root.

The adapter tests (claims -> AccessToken, reject -> None) use a stub validator to
pin :class:`JwtTokenVerifier`'s two jobs: mapping validated claims onto the SDK
``AccessToken`` and turning a validation failure into ``None`` (which FastMCP
renders as a 401). The JWT/JWKS validation itself is covered in ``pipefy_auth``'s
``test_verification.py``. The builder tests pin
:func:`build_resource_server_auth`'s issuer resolution and active/inactive gating.
"""

from __future__ import annotations

from typing import Any

import pytest
from pipefy_auth import JwtValidationSettings, TokenValidationError

from pipefy_mcp.auth import JwtTokenVerifier, build_resource_server_auth
from pipefy_mcp.settings import ResourceServerSettings

_RESOURCE = "https://mcp.example.com/mcp"
_ISSUER = "https://idp.example.com/realms/x"
_EXP = 1893456000


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
            "exp": _EXP,
        }
    )
    token = await JwtTokenVerifier(validator, resource=_RESOURCE).verify_token(
        "the-token"
    )
    assert token is not None
    assert token.token == "the-token"
    assert token.client_id == "client-abc"
    assert token.scopes == ["read", "write"]
    assert token.expires_at == _EXP
    assert token.resource == _RESOURCE


@pytest.mark.unit
async def test_client_id_falls_back_to_client_id_then_sub() -> None:
    by_client_id = await JwtTokenVerifier(
        _StubValidator(claims={"client_id": "cid", "sub": "user-123", "exp": _EXP})
    ).verify_token("t")
    assert by_client_id is not None and by_client_id.client_id == "cid"

    by_sub = await JwtTokenVerifier(
        _StubValidator(claims={"sub": "user-123", "exp": _EXP})
    ).verify_token("t")
    assert by_sub is not None and by_sub.client_id == "user-123"


@pytest.mark.unit
async def test_empty_azp_falls_through_to_next_identity() -> None:
    # Some IdPs emit an empty azp for direct grants; it must not short-circuit
    # the chain to an empty client_id.
    token = await JwtTokenVerifier(
        _StubValidator(claims={"azp": "", "client_id": "cid", "exp": _EXP})
    ).verify_token("t")
    assert token is not None and token.client_id == "cid"


@pytest.mark.unit
async def test_no_client_identity_returns_none() -> None:
    # A token with no azp/client_id/sub carries no usable identity; reject it
    # rather than stamp an anonymous "" client_id.
    token = await JwtTokenVerifier(
        _StubValidator(claims={"scope": "read", "exp": _EXP})
    ).verify_token("t")
    assert token is None


@pytest.mark.unit
async def test_missing_exp_returns_none() -> None:
    # The validator requires exp; if one ever reaches the mapping without it,
    # reject rather than emit a never-expiring token.
    token = await JwtTokenVerifier(
        _StubValidator(claims={"sub": "user-123"})
    ).verify_token("t")
    assert token is None


@pytest.mark.unit
async def test_missing_scope_claim_yields_empty_scopes() -> None:
    token = await JwtTokenVerifier(
        _StubValidator(claims={"sub": "user-123", "exp": _EXP})
    ).verify_token("t")
    assert token is not None and token.scopes == []


@pytest.mark.unit
async def test_scope_claim_as_list_maps_to_scopes() -> None:
    # RFC 9068 specifies a space-delimited string, but some IdPs emit an array;
    # it must map rather than crash (a list has no .split()).
    token = await JwtTokenVerifier(
        _StubValidator(
            claims={"sub": "user-123", "scope": ["read", "write"], "exp": _EXP}
        )
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


# --- build_resource_server_auth: the composition root ---


@pytest.mark.unit
def test_build_stamps_resource_server_url_not_audience() -> None:
    """The verifier stamps this server's resource_server_url onto AccessToken.

    The RFC 9728 metadata advertises resource_server_url as the resource, so the
    token's stamped resource must match it, not the (often unset) audience.
    """
    verifier, _ = build_resource_server_auth(
        ResourceServerSettings(resource_server_url=_RESOURCE),
        # audience set and distinct from resource_server_url: the stamped resource
        # must follow resource_server_url, not audience.
        JwtValidationSettings(
            audience="urn:some-other-audience",
            jwks_uri="https://idp.example.com/jwks",
        ),
        default_issuer_url=_ISSUER,
    )
    assert verifier._resource == _RESOURCE


@pytest.mark.unit
def test_build_inactive_when_unconfigured() -> None:
    """No resource_server_url means no auth: the profile is off, not an error."""
    assert (
        build_resource_server_auth(
            ResourceServerSettings(),
            JwtValidationSettings(),
            default_issuer_url=_ISSUER,
        )
        is None
    )


@pytest.mark.unit
def test_build_issuer_defaults_to_login_issuer() -> None:
    """With no inbound override, the inbound issuer is the login issuer."""
    _, auth = build_resource_server_auth(
        ResourceServerSettings(resource_server_url=_RESOURCE),
        JwtValidationSettings(jwks_uri="https://idp.example.com/jwks"),
        default_issuer_url=_ISSUER,
    )
    assert str(auth.issuer_url).rstrip("/") == _ISSUER


@pytest.mark.unit
def test_build_inbound_issuer_overrides_login_issuer() -> None:
    """An explicit inbound issuer wins over the login issuer."""
    override = "https://other-idp.example.com/realms/y"
    _, auth = build_resource_server_auth(
        ResourceServerSettings(resource_server_url=_RESOURCE),
        JwtValidationSettings(
            issuer_url=override, jwks_uri="https://other-idp.example.com/jwks"
        ),
        default_issuer_url=_ISSUER,
    )
    assert str(auth.issuer_url).rstrip("/") == override


@pytest.mark.unit
def test_build_without_resolvable_issuer_raises() -> None:
    """resource_server_url set but no issuer (override or login) is a misconfiguration."""
    with pytest.raises(RuntimeError, match="no inbound issuer"):
        build_resource_server_auth(
            ResourceServerSettings(resource_server_url=_RESOURCE),
            JwtValidationSettings(),
            default_issuer_url=None,
        )
