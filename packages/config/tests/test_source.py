"""Tests for ``pipefy_config.source.PipefyTomlConfigSource``."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipefy_config.source import PipefyTomlConfigSource


class _Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    alpha: str = Field(default="default-alpha")
    beta: int = Field(default=0)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            PipefyTomlConfigSource(settings_cls),
            file_secret_settings,
        )


def _write_config(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_missing_file_yields_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "does-not-exist.toml"))
    settings = _Settings()
    assert settings.alpha == "default-alpha"
    assert settings.beta == 0


def test_valid_file_populates_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_config(
        tmp_path / "config.toml",
        'alpha = "from-toml"\nbeta = 42\n',
    )
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    settings = _Settings()
    assert settings.alpha == "from-toml"
    assert settings.beta == 42


def test_unknown_keys_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write_config(
        tmp_path / "config.toml",
        'alpha = "ok"\nunrelated_key = "ignored"\n',
    )
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    settings = _Settings()
    assert settings.alpha == "ok"


def test_invalid_toml_raises_value_error_quoting_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_config(tmp_path / "config.toml", "alpha = \n")
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    with pytest.raises(ValueError, match=str(path)):
        _Settings()


def test_env_overrides_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write_config(tmp_path / "config.toml", 'alpha = "from-toml"\n')
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))

    class _EnvSettings(_Settings):
        model_config = SettingsConfigDict(
            env_prefix="MYAPP_", extra="ignore", populate_by_name=True
        )

    monkeypatch.setenv("MYAPP_ALPHA", "from-env")
    assert _EnvSettings().alpha == "from-env"


def test_init_kwargs_override_toml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_config(tmp_path / "config.toml", 'alpha = "from-toml"\n')
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    assert _Settings(alpha="from-init").alpha == "from-init"


def test_lazy_path_resolution_picks_up_env_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = _write_config(tmp_path / "a" / "config.toml", 'alpha = "first"\n')
    second = _write_config(tmp_path / "b" / "config.toml", 'alpha = "second"\n')

    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(first))
    assert _Settings().alpha == "first"

    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(second))
    assert _Settings().alpha == "second"
