"""Unit tests for ``pipefy_auth.verification``: inbound RS256 bearer validation."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from pipefy_auth.verification import JwtValidator, TokenValidationError

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
        "audience": _AUDIENCE,
        "verify_audience": False,
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
    validator = _validator(monkeypatch, verify_audience=True)
    with pytest.raises(TokenValidationError):
        validator.validate(_sign(_claims(aud="https://other.example.com")))


@pytest.mark.unit
def test_wrong_audience_passes_when_not_verifying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The toggle: the same wrong-aud token the previous test rejects is accepted
    # when verify_audience is off (the same-audience interim).
    validator = _validator(monkeypatch, verify_audience=False)
    claims = validator.validate(_sign(_claims(aud="https://other.example.com")))
    assert claims["aud"] == "https://other.example.com"


@pytest.mark.unit
def test_jwks_uri_resolved_from_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    # With no explicit jwks_uri, the validator reads it from the issuer's
    # discovery document.
    metadata = SimpleNamespace(jwks_uri=_JWKS_URI)
    monkeypatch.setattr(
        "pipefy_auth.verification.fetch_provider_metadata",
        lambda issuer_url, policy: metadata,
    )
    validator = JwtValidator(
        issuer_url=_ISSUER, audience=_AUDIENCE, verify_audience=False
    )
    assert validator._jwks.uri == _JWKS_URI


@pytest.mark.unit
def test_discovery_without_jwks_uri_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pipefy_auth.verification.fetch_provider_metadata",
        lambda issuer_url, policy: SimpleNamespace(jwks_uri=None),
    )
    with pytest.raises(ValueError, match="jwks_uri"):
        JwtValidator(issuer_url=_ISSUER, audience=_AUDIENCE, verify_audience=False)
