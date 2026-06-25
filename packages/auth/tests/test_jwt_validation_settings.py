"""Unit tests for ``pipefy_auth.JwtValidationSettings``: inbound-validation config."""

from __future__ import annotations

import pytest

from pipefy_auth import JwtValidationSettings

_ISSUER = "https://idp.example.com/realms/x"


@pytest.fixture(autouse=True)
def _clear_inbound_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate from the ambient environment so defaults are exercised."""
    for key in (
        "PIPEFY_JWT_ISSUER_URL",
        "PIPEFY_JWT_AUDIENCE",
        "PIPEFY_JWT_VERIFY_AUDIENCE",
        "PIPEFY_JWT_JWKS_URI",
        "PIPEFY_ALLOW_INSECURE_URLS",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.unit
def test_defaults_are_inactive_and_safe():
    """Unset is a valid, empty config: no issuer override, audience off."""
    settings = JwtValidationSettings()
    assert settings.issuer_url is None
    assert settings.audience is None
    assert settings.verify_audience is False
    assert settings.jwks_uri is None
    assert settings.allow_insecure_urls is False


@pytest.mark.unit
def test_resolve_issuer_url_prefers_override():
    """An explicit issuer wins over the supplied login-issuer default."""
    settings = JwtValidationSettings(issuer_url=_ISSUER, jwks_uri=None)
    assert settings.resolve_issuer_url("https://login.example.com/realms/y") == _ISSUER


@pytest.mark.unit
def test_resolve_issuer_url_falls_back_to_default():
    """With no override, the inbound issuer is the login issuer."""
    settings = JwtValidationSettings()
    assert settings.resolve_issuer_url(_ISSUER) == _ISSUER


@pytest.mark.unit
def test_resolve_issuer_url_is_none_when_neither_set():
    """No override and no login issuer leaves the inbound issuer unresolved."""
    assert JwtValidationSettings().resolve_issuer_url(None) is None


@pytest.mark.unit
def test_verify_audience_requires_audience():
    """Turning on audience checks without an audience is a misconfiguration."""
    with pytest.raises(ValueError, match="verify_audience requires audience"):
        JwtValidationSettings(verify_audience=True)


@pytest.mark.unit
def test_issuer_url_is_stripped():
    """Surrounding whitespace is stripped so it cannot survive into jwt.decode."""
    settings = JwtValidationSettings(issuer_url=f"  {_ISSUER}  ")
    assert settings.issuer_url == _ISSUER


@pytest.mark.unit
def test_issuer_url_rejects_query_or_fragment():
    """A query/fragment would corrupt the .well-known concatenation."""
    with pytest.raises(ValueError):
        JwtValidationSettings(issuer_url=f"{_ISSUER}?foo=bar")


@pytest.mark.unit
def test_insecure_issuer_rejected_without_allow_flag():
    """http:// issuers are rejected unless the shared insecure flag is set."""
    with pytest.raises(ValueError):
        JwtValidationSettings(issuer_url="http://idp.internal/realms/x")


@pytest.mark.unit
def test_insecure_issuer_allowed_with_shared_env_flag(monkeypatch: pytest.MonkeyPatch):
    """allow_insecure_urls reads the shared PIPEFY_ALLOW_INSECURE_URLS var."""
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "true")
    settings = JwtValidationSettings(issuer_url="http://127.0.0.1:8080/realms/x")
    assert settings.allow_insecure_urls is True
    assert settings.issuer_url == "http://127.0.0.1:8080/realms/x"
