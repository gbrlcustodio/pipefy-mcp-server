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

from pipefy_mcp.auth import (
    JwtTokenVerifier,
    ResourceServer,
    build_resource_server_auth,
)

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
    assert token.sub == "user-123"
    assert token.scopes == ["read", "write"]
    assert token.expires_at == _EXP
    assert token.resource == _RESOURCE


@pytest.mark.unit
async def test_sub_is_none_when_claim_absent() -> None:
    token = await JwtTokenVerifier(
        _StubValidator(claims={"azp": "client-abc", "exp": _EXP})
    ).verify_token("t")
    assert token is not None
    assert token.client_id == "client-abc"
    assert token.sub is None


@pytest.mark.unit
async def test_sub_preserved_when_azp_is_client_id() -> None:
    token = await JwtTokenVerifier(
        _StubValidator(claims={"azp": "client-abc", "sub": "user-123", "exp": _EXP})
    ).verify_token("t")
    assert token is not None
    assert token.client_id == "client-abc"
    assert token.sub == "user-123"


@pytest.mark.unit
async def test_non_string_sub_degrades_to_none_instead_of_rejecting() -> None:
    """sub feeds logging only; a malformed sub must not reject a valid token."""
    token = await JwtTokenVerifier(
        _StubValidator(claims={"azp": "client-abc", "sub": 12345, "exp": _EXP})
    ).verify_token("t")
    assert token is not None
    assert token.client_id == "client-abc"
    assert token.sub is None


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
        ResourceServer.from_url(_RESOURCE),
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
def test_build_advertises_the_parsed_resource_url_in_the_metadata() -> None:
    """AuthSettings' resource_server_url comes from the parsed ResourceServer carrier."""
    _, auth = build_resource_server_auth(
        ResourceServer.from_url(_RESOURCE),
        JwtValidationSettings(jwks_uri="https://idp.example.com/jwks"),
        default_issuer_url=_ISSUER,
    )
    assert str(auth.resource_server_url).rstrip("/") == _RESOURCE


@pytest.mark.unit
def test_build_skips_audience_by_default() -> None:
    """No audience config folds to SkipAudience: the validator does not check aud."""
    verifier, _ = build_resource_server_auth(
        ResourceServer.from_url(_RESOURCE),
        JwtValidationSettings(jwks_uri="https://idp.example.com/jwks"),
        default_issuer_url=_ISSUER,
    )
    assert verifier._validator._verify_aud is False
    assert verifier._validator._audience is None


@pytest.mark.unit
def test_build_requires_audience_when_verifying() -> None:
    """verify_audience with an audience folds to RequireAudience(audience)."""
    verifier, _ = build_resource_server_auth(
        ResourceServer.from_url(_RESOURCE),
        JwtValidationSettings(
            audience="api://x",
            verify_audience=True,
            jwks_uri="https://idp.example.com/jwks",
        ),
        default_issuer_url=_ISSUER,
    )
    assert verifier._validator._verify_aud is True
    assert verifier._validator._audience == "api://x"


@pytest.mark.unit
def test_build_issuer_defaults_to_login_issuer() -> None:
    """With no inbound override, the inbound issuer is the login issuer."""
    _, auth = build_resource_server_auth(
        ResourceServer.from_url(_RESOURCE),
        JwtValidationSettings(jwks_uri="https://idp.example.com/jwks"),
        default_issuer_url=_ISSUER,
    )
    assert str(auth.issuer_url).rstrip("/") == _ISSUER


@pytest.mark.unit
def test_build_inbound_issuer_overrides_login_issuer() -> None:
    """An explicit inbound issuer wins over the login issuer."""
    override = "https://other-idp.example.com/realms/y"
    _, auth = build_resource_server_auth(
        ResourceServer.from_url(_RESOURCE),
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
            ResourceServer.from_url(_RESOURCE),
            JwtValidationSettings(),
            default_issuer_url=None,
        )


# --- ResourceServer.from_url (host-authority parsing) -------------------------


@pytest.mark.unit
def test_resource_server_keeps_the_verbatim_url_and_derives_bare_host() -> None:
    resource = ResourceServer.from_url("https://mcp.pipefy.com/mcp")
    assert resource.url == "https://mcp.pipefy.com/mcp"
    assert resource.host_forms == ("mcp.pipefy.com",)


@pytest.mark.unit
def test_resource_server_adds_host_port_when_url_names_a_port() -> None:
    resource = ResourceServer.from_url("https://mcp.pipefy.com:8443/mcp")
    assert resource.host_forms == ("mcp.pipefy.com", "mcp.pipefy.com:8443")


@pytest.mark.unit
def test_resource_server_brackets_an_ipv6_literal() -> None:
    """urlparse reports the host unbracketed; the wire Host is bracketed."""
    resource = ResourceServer.from_url("https://[2001:db8::1]:8443/mcp")
    assert resource.host_forms == ("[2001:db8::1]", "[2001:db8::1]:8443")
