"""Unit tests for ``pipefy_auth.env`` loaders (auth env edge)."""

from __future__ import annotations

import os

import pytest
from pipefy_infra.deployment import DeploymentConfig

from pipefy_auth.env import DEFAULT_ISSUER_URL, load_auth, load_jwt_validation


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    for key in list(os.environ):
        if key.startswith("PIPEFY_") or key in {"XDG_CONFIG_HOME", "APPDATA"}:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "absent.toml"))
    monkeypatch.chdir(tmp_path)


_DEPLOYMENT = DeploymentConfig(base_url="https://app.pipefy.com")


@pytest.mark.unit
def test_load_auth_defaults() -> None:
    sources, keychain = load_auth(_DEPLOYMENT)
    assert sources.static_token is None
    assert sources.service_account is None
    assert sources.oidc_client is not None
    assert sources.oidc_client.issuer_url == DEFAULT_ISSUER_URL
    assert keychain == "auto"


@pytest.mark.unit
def test_load_auth_reads_static_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPEFY_TOKEN", "bearer-xyz")
    sources, _ = load_auth(_DEPLOYMENT)
    assert sources.static_token == "bearer-xyz"


@pytest.mark.unit
def test_load_auth_builds_service_account_with_derived_token_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")
    sources, _ = load_auth(_DEPLOYMENT)
    assert sources.service_account is not None
    assert sources.service_account.token_url == "https://app.pipefy.com/oauth/token"
    assert sources.service_account.client_id == "cid"


@pytest.mark.unit
def test_load_auth_partial_service_account_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    with pytest.raises(ValueError, match="both"):
        load_auth(_DEPLOYMENT)


@pytest.mark.unit
def test_load_auth_disable_stored_session_drops_oidc_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPEFY_AUTH_DISABLE_STORED_SESSION", "true")
    sources, _ = load_auth(_DEPLOYMENT)
    assert sources.oidc_client is None


@pytest.mark.unit
def test_load_auth_folds_keychain_backend_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPEFY_AUTH_KEYCHAIN_BACKEND", "FILE")
    _sources, keychain = load_auth(_DEPLOYMENT)
    assert keychain == "file"


@pytest.mark.unit
def test_load_jwt_validation_returns_none_without_issuer() -> None:
    assert load_jwt_validation(_DEPLOYMENT, default_issuer_url=None) is None


@pytest.mark.unit
def test_load_jwt_validation_falls_back_to_default_issuer() -> None:
    inputs = load_jwt_validation(_DEPLOYMENT, default_issuer_url=DEFAULT_ISSUER_URL)
    assert inputs is not None
    assert inputs.issuer_url == DEFAULT_ISSUER_URL


@pytest.mark.unit
def test_load_jwt_validation_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPEFY_JWT_ISSUER_URL", "https://other.example.com/realms/x")
    inputs = load_jwt_validation(_DEPLOYMENT, default_issuer_url=DEFAULT_ISSUER_URL)
    assert inputs is not None
    assert inputs.issuer_url == "https://other.example.com/realms/x"
