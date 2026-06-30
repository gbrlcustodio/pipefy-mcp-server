"""Unit tests for ``JwtValidationInputs`` (the inbound-validation witness)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipefy_auth.verification import JwtValidationInputs

_ISSUER = "https://idp.example.com/realms/pipefy"


@pytest.mark.unit
def test_minimal_inputs_default_audience_off() -> None:
    inputs = JwtValidationInputs(issuer_url=_ISSUER)
    assert inputs.issuer_url == _ISSUER
    assert inputs.verify_audience is False
    assert inputs.audience is None


@pytest.mark.unit
def test_verify_audience_requires_audience() -> None:
    with pytest.raises(ValidationError, match="verify_audience requires audience"):
        JwtValidationInputs(issuer_url=_ISSUER, verify_audience=True)


@pytest.mark.unit
def test_verify_audience_with_audience_is_accepted() -> None:
    inputs = JwtValidationInputs(
        issuer_url=_ISSUER, verify_audience=True, audience="aud"
    )
    assert inputs.verify_audience is True
    assert inputs.audience == "aud"


@pytest.mark.unit
def test_issuer_is_required() -> None:
    with pytest.raises(ValidationError):
        JwtValidationInputs()


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["not-a-url", "ftp://idp.example.com"])
def test_rejects_non_url_issuer(bad: str) -> None:
    with pytest.raises(ValidationError, match="should match pattern"):
        JwtValidationInputs(issuer_url=bad)


@pytest.mark.unit
def test_rejects_issuer_with_query_or_fragment() -> None:
    with pytest.raises(ValidationError, match="query string or fragment"):
        JwtValidationInputs(issuer_url=f"{_ISSUER}?x=1")


@pytest.mark.unit
def test_rejects_jwks_uri_with_query_or_fragment() -> None:
    with pytest.raises(ValidationError, match="query string or fragment"):
        JwtValidationInputs(issuer_url=_ISSUER, jwks_uri=f"{_ISSUER}/certs#frag")


@pytest.mark.unit
def test_is_frozen() -> None:
    inputs = JwtValidationInputs(issuer_url=_ISSUER)
    with pytest.raises(ValidationError):
        inputs.verify_audience = True
