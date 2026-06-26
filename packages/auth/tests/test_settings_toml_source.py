"""Auth ``config.toml`` loading via the ``read_auth_env`` edge reader.

TOML reading moved out of ``AuthSettings`` (now a pure value object) into the
edge reader :func:`pipefy_infra.config.read_auth_env`. These tests exercise the
precedence tiers (env > ``.env`` > TOML), the bare-field-name TOML keys auth
feeds, and the value-object hand-off. The reader's own unit coverage lives in
``packages/infra/tests/test_edge_readers.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pipefy_infra.config import read_auth_env

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
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "config.toml"))


def test_field_name_keys_load_from_toml(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
        issuer_url = "https://signin-staging.pipefy.com/realms/pipefy"
        client_id = "staging-client"
        """,
    )
    raw = read_auth_env()
    assert raw["issuer_url"] == "https://signin-staging.pipefy.com/realms/pipefy"
    assert raw["client_id"] == "staging-client"


def test_credentials_load_from_toml(tmp_path: Path) -> None:
    # TOML keys are bare field names -- ``static_token``, not ``PIPEFY_TOKEN``.
    _write(
        tmp_path / "config.toml",
        """
        static_token = "tom-token"
        service_account_client_id = "svc-id"
        service_account_client_secret = "svc-secret"
        """,
    )
    raw = read_auth_env()
    assert raw["static_token"] == "tom-token"
    assert raw["service_account_client_id"] == "svc-id"
    assert raw["service_account_client_secret"] == "svc-secret"


def test_env_wins_over_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(tmp_path / "config.toml", 'issuer_url = "https://from-toml.example"\n')
    monkeypatch.setenv("PIPEFY_AUTH_ISSUER_URL", "https://from-env.example")
    assert read_auth_env()["issuer_url"] == "https://from-env.example"


def test_dotenv_wins_over_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # chdir so ``env_file=".env"`` resolves to tmp_path. ``test_env_wins_over_toml``
    # does NOT cover this tier: a reorder sliding TOML between env and dotenv
    # would pass while silently flipping dotenv > toml precedence.
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".env", "PIPEFY_AUTH_ISSUER_URL=https://from-dotenv.example\n")
    _write(tmp_path / "config.toml", 'issuer_url = "https://from-toml.example"\n')
    assert read_auth_env()["issuer_url"] == "https://from-dotenv.example"


def test_missing_file_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # PIPEFY_CONFIG_FILE points at a non-existent path; the reader returns an
    # empty mapping and the value object supplies the defaults.
    assert read_auth_env() == {}
    settings = AuthSettings(**read_auth_env())
    assert settings.issuer_url == "https://signin.pipefy.com/realms/pipefy"


def test_invalid_toml_raises_value_error_quoting_path(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "issuer_url = \n")
    with pytest.raises(ValueError, match=str(path)):
        read_auth_env()


def test_unknown_keys_ignored(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
        issuer_url = "https://signin-staging.pipefy.com/realms/pipefy"
        not_a_known_field = "ignored"
        """,
    )
    raw = read_auth_env()
    assert raw["issuer_url"] == "https://signin-staging.pipefy.com/realms/pipefy"
    assert "not_a_known_field" not in raw


def test_kill_switch_and_backend_load_from_toml(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
        disable_stored_session = true
        keychain_backend = "file"
        """,
    )
    settings = AuthSettings(**read_auth_env())
    assert settings.disable_stored_session is True
    assert settings.keychain_backend == "file"
    assert settings.to_oidc_client() is None


def test_env_wins_over_toml_for_kill_switch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``PIPEFY_AUTH_DISABLE_STORED_SESSION=0`` flips the TOML-set ``true`` back off."""
    _write(tmp_path / "config.toml", "disable_stored_session = true\n")
    monkeypatch.setenv("PIPEFY_AUTH_DISABLE_STORED_SESSION", "0")
    assert read_auth_env()["disable_stored_session"] is False


def test_env_alias_names_not_picked_up_from_toml(tmp_path: Path) -> None:
    # The credential env names (e.g. PIPEFY_TOKEN) are env-only; TOML uses field
    # names. Pasting the env-shaped key into TOML must NOT populate the field,
    # exercising the "TOML keys are bare field names" rule.
    _write(
        tmp_path / "config.toml",
        """
        PIPEFY_TOKEN = "should-be-ignored"
        """,
    )
    assert "static_token" not in read_auth_env()
