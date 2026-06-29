"""Auth edge-reader end-to-end loading: ``[auth]`` / ``[service_account]`` / ``[jwt]`` TOML.

The auth library is env-free; ``_edge_readers`` provides the test stand-ins for
the application edge. These tests lock the sectioned-TOML layout that resolves
the ``issuer_url`` key collision (an ``[auth]`` issuer must not feed the inbound
``[jwt]`` reader, and vice versa) and the env / dotenv precedence as observed
through those readers.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from _edge_readers import (
    AuthSettings,
    DeploymentSettings,
    JwtValidationSettings,
    ServiceAccountSettings,
)

from pipefy_auth.config import DEFAULT_ISSUER_URL


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point PIPEFY_CONFIG_FILE at the test tmpdir + clear all PIPEFY_* env."""
    for key in list(os.environ):
        if key.startswith("PIPEFY_") or key in {"XDG_CONFIG_HOME", "APPDATA"}:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "config.toml"))


def _auth() -> AuthSettings:
    return AuthSettings(deployment=DeploymentSettings())


def test_auth_section_keys_load_from_toml(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
        [auth]
        issuer_url = "https://signin-staging.pipefy.com/realms/pipefy"
        public_client_id = "staging-client"
        """,
    )
    settings = _auth()
    assert settings.issuer_url == "https://signin-staging.pipefy.com/realms/pipefy"
    assert settings.public_client_id == "staging-client"


def test_base_url_loads_top_level_into_deployment(tmp_path: Path) -> None:
    _write(tmp_path / "config.toml", 'base_url = "https://staging.pipefy.com"\n')
    assert DeploymentSettings().base_url == "https://staging.pipefy.com"


def test_static_token_loads_from_auth_section_bare_key(tmp_path: Path) -> None:
    # TOML uses the bare field name; the PIPEFY_TOKEN alias is env-only.
    _write(tmp_path / "config.toml", '[auth]\nstatic_token = "tom-token"\n')
    assert _auth().static_token == "tom-token"


def test_static_token_loads_from_env_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPEFY_TOKEN", "env-token")
    assert _auth().static_token == "env-token"


def test_edge_strips_surrounding_whitespace_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The edge readers own whitespace trimming (the library value objects
    # reject a padded value). A trailing newline from ``$(...)`` or a padded
    # value is normalized as it is read, so the clean value reaches the model.
    monkeypatch.setenv("PIPEFY_AUTH_ISSUER_URL", "  https://idp.example/realms/x \n")
    monkeypatch.setenv("PIPEFY_TOKEN", "\ttok\t")
    settings = _auth()
    assert settings.issuer_url == "https://idp.example/realms/x"
    assert settings.static_token == "tok"


def test_edge_strips_whitespace_before_building_service_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "  svc-id  ")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "svc-secret\n")
    creds = ServiceAccountSettings().to_credentials()
    assert creds is not None
    assert creds.client_id == "svc-id"
    assert creds.client_secret == "svc-secret"


def test_edge_folds_keychain_backend_case_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The inherited whitespace trim and the per-field fold compose, so a padded
    # uppercase value still lands clean.
    monkeypatch.setenv("PIPEFY_AUTH_KEYCHAIN_BACKEND", " FILE ")
    assert _auth().keychain_backend == "file"


def test_service_account_section_builds_credentials(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
        [service_account]
        client_id = "svc-id"
        client_secret = "svc-secret"
        """,
    )
    creds = ServiceAccountSettings().to_credentials()
    assert creds is not None
    assert creds.client_id == "svc-id"
    assert creds.client_secret == "svc-secret"


def test_env_wins_over_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        '[auth]\nissuer_url = "https://from-toml.example"\n',
    )
    monkeypatch.setenv("PIPEFY_AUTH_ISSUER_URL", "https://from-env.example")
    assert _auth().issuer_url == "https://from-env.example"


def test_dotenv_wins_over_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".env", "PIPEFY_AUTH_ISSUER_URL=https://from-dotenv.example\n")
    _write(
        tmp_path / "config.toml",
        '[auth]\nissuer_url = "https://from-toml.example"\n',
    )
    assert _auth().issuer_url == "https://from-dotenv.example"


def test_missing_file_uses_defaults() -> None:
    assert _auth().issuer_url == DEFAULT_ISSUER_URL
    assert DeploymentSettings().base_url == "https://app.pipefy.com"


def test_invalid_toml_raises_value_error_quoting_path(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "[auth]\nissuer_url = \n")
    with pytest.raises(ValueError, match=str(path)):
        _auth()


def test_kill_switch_and_backend_load_from_auth_section(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
        [auth]
        disable_stored_session = true
        keychain_backend = "file"
        """,
    )
    settings = _auth()
    assert settings.disable_stored_session is True
    assert settings.keychain_backend == "file"
    assert settings.to_oidc_client() is None


def test_issuer_url_collision_top_level_does_not_feed_auth(tmp_path: Path) -> None:
    # A top-level ``issuer_url`` (or one under ``[jwt]``) must NOT populate the
    # ``[auth]`` reader: this is the collision guard the sectioning buys.
    _write(
        tmp_path / "config.toml",
        """
        issuer_url = "https://top-level.example"
        [jwt]
        issuer_url = "https://jwt-only.example"
        """,
    )
    assert _auth().issuer_url == DEFAULT_ISSUER_URL


def test_jwt_section_feeds_only_jwt_reader(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
        [auth]
        issuer_url = "https://auth-only.example/realms/x"
        [jwt]
        issuer_url = "https://jwt-only.example/realms/x"
        """,
    )
    assert _auth().issuer_url == "https://auth-only.example/realms/x"
    assert (
        JwtValidationSettings(deployment=DeploymentSettings()).issuer_url
        == "https://jwt-only.example/realms/x"
    )


# --- ServiceAccountSettings.to_credentials() both-or-neither rule ---------------


def test_to_credentials_both_unset_returns_none() -> None:
    assert ServiceAccountSettings().to_credentials() is None


def test_to_credentials_both_set_returns_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "id")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "secret")
    creds = ServiceAccountSettings().to_credentials()
    assert creds is not None
    assert (creds.client_id, creds.client_secret) == ("id", "secret")


@pytest.mark.parametrize(
    "env_key",
    ["PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET"],
)
def test_to_credentials_exactly_one_set_raises(
    monkeypatch: pytest.MonkeyPatch, env_key: str
) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv(env_key, "only-one")
    with pytest.raises(ValidationError):
        ServiceAccountSettings().to_credentials()
