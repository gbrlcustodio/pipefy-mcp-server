"""Unit tests for ``pipefy_auth.verification``: inbound RS256 bearer validation."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from pipefy_auth.verification import (
    JwtValidator,
    RequireAudience,
    SkipAudience,
    TokenValidationError,
)

_ISSUER = "https://idp.example.com/realms/pipefy"
_AUDIENCE = "https://mcp.example.com/mcp"
_JWKS_URI = "https://idp.example.com/protocol/openid-connect/certs"

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _sign(claims: dict[str, Any], *, key: rsa.RSAPrivateKey = _PRIVATE_KEY) -> str:
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})


def _claims(**overrides: Any) -> dict[str, Any]:
    base = {
        "iss": _ISSUER,
        "sub": "user-123",
        "azp": "client-abc",
        "scope": "read write",
        "exp": int(time.time()) + 3600,
        "aud": _AUDIENCE,
    }
    base.update(overrides)
    return base


def _validator(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> JwtValidator:
    """Build a validator whose JWKS lookup returns the in-test public key.

    The explicit ``jwks_uri`` skips discovery (no network at construction); the
    monkeypatch returns the signing key without an HTTP fetch.
    """
    defaults = {
        "issuer_url": _ISSUER,
        "audience_policy": SkipAudience(),
        "jwks_uri": _JWKS_URI,
    }
    defaults.update(kwargs)
    validator = JwtValidator(**defaults)
    monkeypatch.setattr(
        validator._jwks,
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=_PRIVATE_KEY.public_key()),
    )
    return validator


@pytest.mark.unit
def test_valid_token_returns_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = _validator(monkeypatch)
    claims = validator.validate(_sign(_claims()))
    assert claims["sub"] == "user-123"
    assert claims["azp"] == "client-abc"
    assert claims["scope"] == "read write"


@pytest.mark.unit
def test_tampered_signature_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = _validator(monkeypatch)
    token = _sign(_claims())
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}AAAA"
    with pytest.raises(TokenValidationError):
        validator.validate(tampered)


@pytest.mark.unit
def test_token_signed_by_unknown_key_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _validator(monkeypatch)
    # Signed by a key whose public half is not what the JWKS returns.
    with pytest.raises(TokenValidationError):
        validator.validate(_sign(_claims(), key=_OTHER_KEY))


@pytest.mark.unit
def test_expired_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = _validator(monkeypatch)
    with pytest.raises(TokenValidationError):
        validator.validate(_sign(_claims(exp=int(time.time()) - 3600)))


@pytest.mark.unit
def test_wrong_issuer_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = _validator(monkeypatch)
    with pytest.raises(TokenValidationError):
        validator.validate(_sign(_claims(iss="https://evil.example.com/realms/x")))


@pytest.mark.unit
def test_wrong_audience_is_rejected_when_verifying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _validator(monkeypatch, audience_policy=RequireAudience(_AUDIENCE))
    with pytest.raises(TokenValidationError):
        validator.validate(_sign(_claims(aud="https://other.example.com")))


@pytest.mark.unit
def test_wrong_audience_passes_when_not_verifying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The toggle: the same wrong-aud token the previous test rejects is accepted
    # when audience verification is off (the same-audience interim).
    validator = _validator(monkeypatch, audience_policy=SkipAudience())
    claims = validator.validate(_sign(_claims(aud="https://other.example.com")))
    assert claims["aud"] == "https://other.example.com"


@pytest.mark.unit
def test_jwks_uri_resolved_from_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    # With no explicit jwks_uri, the validator reads it from the issuer's
    # discovery document, lazily on first use rather than at construction.
    metadata = SimpleNamespace(jwks_uri=_JWKS_URI)
    monkeypatch.setattr(
        "pipefy_auth.verification.fetch_provider_metadata",
        lambda issuer_url, policy: metadata,
    )
    validator = JwtValidator(issuer_url=_ISSUER, audience_policy=SkipAudience())
    assert validator._jwks is None  # deferred, not resolved at construction
    assert validator._jwks_client().uri == _JWKS_URI


@pytest.mark.unit
def test_discovery_path_does_no_network_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Construction must not touch the IdP, so process boot never blocks on it.
    # A discovery that would raise leaves construction untouched; the failure
    # only surfaces on validate().
    def _fail(issuer_url: str, policy: Any) -> SimpleNamespace:
        raise AssertionError("discovery must not run at construction")

    monkeypatch.setattr("pipefy_auth.verification.fetch_provider_metadata", _fail)
    validator = JwtValidator(issuer_url=_ISSUER, audience_policy=SkipAudience())
    assert validator._jwks is None


@pytest.mark.unit
def test_discovery_without_jwks_uri_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # The discovery failure now surfaces on validate() (lazy), folded into
    # TokenValidationError, not at construction.
    monkeypatch.setattr(
        "pipefy_auth.verification.fetch_provider_metadata",
        lambda issuer_url, policy: SimpleNamespace(jwks_uri=None),
    )
    validator = JwtValidator(issuer_url=_ISSUER, audience_policy=SkipAudience())
    with pytest.raises(TokenValidationError, match="jwks_uri"):
        validator.validate(_sign(_claims()))


@pytest.mark.unit
def test_discovery_failure_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    # A transient discovery failure must not be cached: the next validate()
    # retries, so the validator self-heals once the IdP is reachable again.
    calls = {"n": 0}

    def _flaky(issuer_url: str, policy: Any) -> SimpleNamespace:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("transient discovery outage")
        return SimpleNamespace(jwks_uri=_JWKS_URI)

    monkeypatch.setattr("pipefy_auth.verification.fetch_provider_metadata", _flaky)
    validator = JwtValidator(issuer_url=_ISSUER, audience_policy=SkipAudience())

    with pytest.raises(TokenValidationError, match="transient discovery outage"):
        validator.validate(_sign(_claims()))
    assert validator._jwks is None  # failure not cached

    # Second attempt: discovery succeeds and the resolved client is reused.
    monkeypatch.setattr(
        validator._jwks_client(),
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=_PRIVATE_KEY.public_key()),
    )
    assert calls["n"] == 2
    claims = validator.validate(_sign(_claims()))
    assert claims["sub"] == "user-123"


@pytest.mark.unit
def test_explicit_http_jwks_uri_is_rejected() -> None:
    # An explicit jwks_uri skips discovery; the primitive still enforces the
    # https/SSRF gate rather than handing an unchecked URL to PyJWKClient.
    with pytest.raises(ValueError, match="jwks_uri"):
        JwtValidator(
            issuer_url=_ISSUER,
            audience_policy=SkipAudience(),
            jwks_uri="http://idp.example.com/protocol/openid-connect/certs",
        )


@pytest.mark.unit
def test_explicit_internal_host_jwks_uri_is_rejected() -> None:
    with pytest.raises(ValueError, match="jwks_uri"):
        JwtValidator(
            issuer_url=_ISSUER,
            audience_policy=SkipAudience(),
            jwks_uri="https://127.0.0.1/certs",
        )


@pytest.mark.unit
def test_explicit_jwks_uri_with_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="jwks_uri"):
        JwtValidator(
            issuer_url=_ISSUER,
            audience_policy=SkipAudience(),
            jwks_uri=f"{_JWKS_URI}?rotate=1",
        )


@pytest.mark.unit
def test_explicit_insecure_jwks_uri_allowed_when_opted_in() -> None:
    # allow_insecure_urls relaxes both the scheme and the internal-host gate,
    # mirroring the discovery path's policy.
    validator = JwtValidator(
        issuer_url=_ISSUER,
        audience_policy=SkipAudience(),
        allow_insecure_urls=True,
        jwks_uri="http://127.0.0.1/certs",
    )
    assert validator._jwks.uri == "http://127.0.0.1/certs"
