"""``PipefySettings`` end-to-end TOML loading via ``PipefyTomlConfigSource``."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipefy_sdk.settings import PipefySettings


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Clear PIPEFY_* env and point PIPEFY_CONFIG_FILE at the test tmpdir."""
    for key in list(os.environ):
        if key.startswith("PIPEFY_") or key in {"XDG_CONFIG_HOME", "APPDATA"}:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "config.toml"))


def test_field_name_keys_load_from_toml(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
        base_url = "https://staging.pipefy.com"
        org_id = "300123"
        default_webhook_name = "Test Hook"
        """,
    )
    settings = PipefySettings()
    assert settings.base_url == "https://staging.pipefy.com"
    assert settings.org_id == "300123"
    assert settings.default_webhook_name == "Test Hook"


def test_service_account_ids_list_from_toml(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        'service_account_ids = ["42", "43", "44"]\n',
    )
    assert PipefySettings().service_account_ids == ["42", "43", "44"]


def test_env_wins_over_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(tmp_path / "config.toml", 'base_url = "https://from-toml.example"\n')
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://from-env.example")
    assert PipefySettings().base_url == "https://from-env.example"


def test_init_kwargs_win_over_toml(tmp_path: Path) -> None:
    _write(tmp_path / "config.toml", 'base_url = "https://from-toml.example"\n')
    assert (
        PipefySettings(base_url="https://from-init.example").base_url
        == "https://from-init.example"
    )


def test_missing_file_uses_defaults() -> None:
    settings = PipefySettings()
    assert settings.base_url == "https://app.pipefy.com"
    assert settings.org_id is None
    assert settings.service_account_ids == []


def test_invalid_toml_raises_value_error_quoting_path(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "base_url = \n")
    with pytest.raises(ValueError, match=str(path)):
        PipefySettings()


def test_unknown_keys_ignored(tmp_path: Path) -> None:
    # Both auth-only keys (e.g. ``auth_url``) and arbitrary keys should be
    # silently dropped by PipefySettings via ``extra="ignore"``.
    _write(
        tmp_path / "config.toml",
        """
        base_url = "https://staging.pipefy.com"
        auth_url = "https://signin-staging.pipefy.com/realms/pipefy"
        completely_unrelated = 42
        """,
    )
    assert PipefySettings().base_url == "https://staging.pipefy.com"


def test_shared_base_url_loads_into_both_models(tmp_path: Path) -> None:
    # Single ``base_url`` key in TOML must populate both AuthSettings and
    # PipefySettings symmetrically — the operator's single-source-of-truth
    # expectation.
    from pipefy_auth.settings import AuthSettings

    _write(tmp_path / "config.toml", 'base_url = "https://shared.example"\n')
    assert PipefySettings().base_url == "https://shared.example"
    assert AuthSettings().base_url == "https://shared.example"
