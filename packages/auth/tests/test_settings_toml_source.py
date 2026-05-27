"""``AuthSettings`` end-to-end TOML loading via ``PipefyTomlConfigSource``."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipefy_auth.settings import AuthSettings


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
    # PIPEFY_CONFIG_FILE points at a tmp file even when the test doesn't write
    # one, so a stale ``~/.config/pipefy/config.toml`` on the dev machine
    # cannot bleed into the model.
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "config.toml"))


def test_field_name_keys_load_from_toml(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
        base_url = "https://staging.pipefy.com"
        auth_url = "https://signin-staging.pipefy.com/realms/pipefy"
        auth_client_id = "staging-client"
        """,
    )
    settings = AuthSettings()
    assert settings.base_url == "https://staging.pipefy.com"
    assert settings.auth_url == "https://signin-staging.pipefy.com/realms/pipefy"
    assert settings.auth_client_id == "staging-client"


def test_credentials_load_from_toml(tmp_path: Path) -> None:
    # TOML keys are bare field names — ``static_token``, not ``PIPEFY_TOKEN``.
    _write(
        tmp_path / "config.toml",
        """
        static_token = "tom-token"
        service_account_client_id = "svc-id"
        service_account_client_secret = "svc-secret"
        """,
    )
    settings = AuthSettings()
    assert settings.static_token == "tom-token"
    assert settings.service_account_client_id == "svc-id"
    assert settings.service_account_client_secret == "svc-secret"


def test_env_wins_over_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(tmp_path / "config.toml", 'base_url = "https://from-toml.example"\n')
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://from-env.example")
    assert AuthSettings().base_url == "https://from-env.example"


def test_dotenv_wins_over_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # chdir so ``env_file=".env"`` resolves to tmp_path. ``test_env_wins_over_toml``
    # does NOT cover this tier: a reorder sliding TOML between env and dotenv
    # would keep it green while silently flipping dotenv > toml.
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".env", "PIPEFY_BASE_URL=https://from-dotenv.example\n")
    _write(tmp_path / "config.toml", 'base_url = "https://from-toml.example"\n')
    assert AuthSettings().base_url == "https://from-dotenv.example"


def test_init_kwargs_win_over_toml(tmp_path: Path) -> None:
    _write(tmp_path / "config.toml", 'base_url = "https://from-toml.example"\n')
    assert (
        AuthSettings(base_url="https://from-init.example").base_url
        == "https://from-init.example"
    )


def test_missing_file_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # PIPEFY_CONFIG_FILE points at a non-existent path; defaults apply.
    settings = AuthSettings()
    assert settings.base_url == "https://app.pipefy.com"
    assert settings.auth_url == "https://signin.pipefy.com/realms/pipefy"


def test_invalid_toml_raises_value_error_quoting_path(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "base_url = \n")
    with pytest.raises(ValueError, match=str(path)):
        AuthSettings()


def test_unknown_keys_ignored(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
        base_url = "https://staging.pipefy.com"
        not_a_known_field = "ignored"
        """,
    )
    assert AuthSettings().base_url == "https://staging.pipefy.com"


def test_kill_switch_and_backend_load_from_toml(tmp_path: Path) -> None:
    """Both new fields populate from bare TOML keys."""
    _write(
        tmp_path / "config.toml",
        """
        disable_stored_session = true
        keychain_backend = "file"
        """,
    )
    settings = AuthSettings()
    assert settings.disable_stored_session is True
    assert settings.keychain_backend == "file"
    assert settings.to_oidc_client() is None


def test_env_wins_over_toml_for_kill_switch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``PIPEFY_DISABLE_STORED_SESSION=0`` flips the TOML-set ``true`` back off."""
    _write(tmp_path / "config.toml", "disable_stored_session = true\n")
    monkeypatch.setenv("PIPEFY_DISABLE_STORED_SESSION", "0")
    settings = AuthSettings()
    assert settings.disable_stored_session is False
    assert settings.to_oidc_client() is not None


def test_legacy_env_var_names_not_picked_up_from_toml(tmp_path: Path) -> None:
    # ``AliasChoices`` lists env-only names (PIPEFY_TOKEN, PIPEFY_OAUTH_CLIENT).
    # TOML uses field names. Pasting the env-shaped key into TOML must NOT
    # populate the field — exercises the "TOML keys are bare field names" rule.
    _write(
        tmp_path / "config.toml",
        """
        PIPEFY_TOKEN = "should-be-ignored"
        PIPEFY_OAUTH_CLIENT = "should-be-ignored"
        """,
    )
    settings = AuthSettings()
    assert settings.static_token is None
    assert settings.service_account_client_id is None
