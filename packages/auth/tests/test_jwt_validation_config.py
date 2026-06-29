"""Unit tests for ``pipefy_auth.JwtValidationConfig``: inbound-validation config.

A pure value object: ``deployment`` is injected (the shared insecure-URL posture
is forwarded off it), and the fields are set with kwargs. Env-name coverage lives
at the application edge; one ``[jwt]`` TOML case here exercises the sectioned
reader end-to-end.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from _edge_readers import DeploymentSettings, JwtValidationSettings
from pipefy_infra.deployment import DeploymentConfig

from pipefy_auth import JwtValidationConfig

_ISSUER = "https://idp.example.com/realms/x"


def _jwt(**kwargs) -> JwtValidationConfig:
    kwargs.setdefault("deployment", DeploymentConfig())
    return JwtValidationConfig(**kwargs)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Clear ambient PIPEFY_* env and point the config file at the tmpdir."""
    for key in list(os.environ):
        if key.startswith("PIPEFY_") or key in {"XDG_CONFIG_HOME", "APPDATA"}:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "config.toml"))


@pytest.mark.unit
def test_defaults_are_inactive_and_safe():
    """Unset is a valid, empty config: no issuer override, audience off."""
    settings = _jwt()
    assert settings.issuer_url is None
    assert settings.audience is None
    assert settings.verify_audience is False
    assert settings.jwks_uri is None
    assert settings.allow_insecure_urls is False


@pytest.mark.unit
def test_requires_injected_deployment():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="deployment"):
        JwtValidationConfig()


@pytest.mark.unit
def test_resolve_issuer_url_prefers_override():
    """An explicit issuer wins over the supplied login-issuer default."""
    settings = _jwt(issuer_url=_ISSUER, jwks_uri=None)
    assert settings.resolve_issuer_url("https://login.example.com/realms/y") == _ISSUER


@pytest.mark.unit
def test_resolve_issuer_url_falls_back_to_default():
    """With no override, the inbound issuer is the login issuer."""
    assert _jwt().resolve_issuer_url(_ISSUER) == _ISSUER


@pytest.mark.unit
def test_resolve_issuer_url_is_none_when_neither_set():
    """No override and no login issuer leaves the inbound issuer unresolved."""
    assert _jwt().resolve_issuer_url(None) is None


@pytest.mark.unit
def test_verify_audience_requires_audience():
    """Turning on audience checks without an audience is a misconfiguration."""
    with pytest.raises(ValueError, match="verify_audience requires audience"):
        _jwt(verify_audience=True)


@pytest.mark.unit
def test_issuer_url_rejects_surrounding_whitespace():
    """The value object rejects padding (the edge trims env input upstream)."""
    with pytest.raises(ValueError):
        _jwt(issuer_url=f"  {_ISSUER}  ")


@pytest.mark.unit
def test_issuer_url_rejects_query_or_fragment():
    """A query/fragment would corrupt the .well-known concatenation."""
    with pytest.raises(ValueError):
        _jwt(issuer_url=f"{_ISSUER}?foo=bar")


@pytest.mark.unit
def test_insecure_issuer_rejected_without_allow_flag():
    """http:// issuers are rejected unless the deployment posture allows it."""
    with pytest.raises(ValueError):
        _jwt(issuer_url="http://idp.internal/realms/x")


@pytest.mark.unit
def test_insecure_issuer_allowed_when_deployment_insecure():
    """allow_insecure_urls forwards off the injected deployment posture."""
    settings = JwtValidationConfig(
        deployment=DeploymentConfig(
            base_url="http://localhost:3000", allow_insecure_urls=True
        ),
        issuer_url="http://127.0.0.1:8080/realms/x",
    )
    assert settings.allow_insecure_urls is True
    assert settings.issuer_url == "http://127.0.0.1:8080/realms/x"


@pytest.mark.unit
def test_jwt_section_loads_from_toml(tmp_path: Path) -> None:
    """The ``[jwt]`` reader loads its fields end-to-end through the TOML source."""
    (tmp_path / "config.toml").write_text(
        """
        [jwt]
        issuer_url = "https://idp.example.com/realms/x"
        audience = "pipefy-api"
        verify_audience = true
        """,
        encoding="utf-8",
    )
    settings = JwtValidationSettings(deployment=DeploymentSettings())
    assert settings.issuer_url == _ISSUER
    assert settings.audience == "pipefy-api"
    assert settings.verify_audience is True


@pytest.mark.unit
def test_jwt_edge_strips_surrounding_whitespace_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The edge reader trims env whitespace before the value reaches the model."""
    monkeypatch.setenv("PIPEFY_JWT_ISSUER_URL", f"  {_ISSUER} \n")
    monkeypatch.setenv("PIPEFY_JWT_AUDIENCE", "  pipefy-api  ")
    settings = JwtValidationSettings(deployment=DeploymentSettings())
    assert settings.issuer_url == _ISSUER
    assert settings.audience == "pipefy-api"
