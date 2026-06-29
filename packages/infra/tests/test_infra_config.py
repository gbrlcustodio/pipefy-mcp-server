"""Tests for ``pipefy_infra.config`` (path discovery + TOML source)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipefy_infra.config import (
    PipefyTomlConfigSource,
    config_dir,
    config_file_path,
)
from pipefy_infra.settings_base import PipefyBaseSettings


def test_config_dir_posix_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    assert config_dir() == tmp_path / ".config" / "pipefy"


def test_config_dir_posix_xdg_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config_dir() == tmp_path / "xdg" / "pipefy"


def test_config_dir_windows_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    assert config_dir() == tmp_path / "AppData" / "Roaming" / "pipefy"


def test_config_dir_windows_appdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    assert config_dir() == tmp_path / "appdata" / "pipefy"


def test_config_file_path_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("PIPEFY_CONFIG_FILE", raising=False)
    assert config_file_path() == tmp_path / "pipefy" / "config.toml"


def test_config_file_path_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    override = tmp_path / "alt" / "custom.toml"
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(override))
    assert config_file_path() == override


def test_config_file_path_blank_env_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", "")
    assert config_file_path() == tmp_path / "pipefy" / "config.toml"


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


class _SectionedSettings(BaseSettings):
    """Reads its keys from a named TOML sub-table rather than the top level."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    alpha: str = Field(default="default-alpha")

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
            PipefyTomlConfigSource(settings_cls, section="auth"),
            file_secret_settings,
        )


def test_section_reads_only_its_sub_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_config(
        tmp_path / "config.toml",
        'alpha = "top-level"\n[auth]\nalpha = "from-auth"\n[jwt]\nalpha = "from-jwt"\n',
    )
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    assert _SectionedSettings().alpha == "from-auth"


def test_section_ignores_top_level_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A top-level ``alpha`` must not feed a sectioned reader: this is the
    # collision guard that lets two readers each own an ``alpha`` / ``issuer_url``.
    path = _write_config(tmp_path / "config.toml", 'alpha = "top-level"\n')
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    assert _SectionedSettings().alpha == "default-alpha"


def test_section_missing_yields_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_config(tmp_path / "config.toml", '[jwt]\nalpha = "from-jwt"\n')
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    assert _SectionedSettings().alpha == "default-alpha"


def test_section_non_table_value_raises_quoting_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_config(tmp_path / "config.toml", 'auth = "not-a-table"\n')
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    with pytest.raises(ValueError, match=str(path)):
        _SectionedSettings()


class _PrefixedReader(PipefyBaseSettings):
    model_config = SettingsConfigDict(env_prefix="PIPEFY_X_")
    _toml_section = "xtable"

    alpha: str = Field(default="default-alpha")


def test_base_settings_merges_shared_config_with_subclass_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The subclass declares only ``env_prefix``; ``extra="ignore"`` /
    # ``populate_by_name`` / the source chain come from PipefyBaseSettings.
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("PIPEFY_X_ALPHA", "from-env")
    assert _PrefixedReader().alpha == "from-env"


def test_base_settings_reads_its_toml_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_config(
        tmp_path / "config.toml",
        'alpha = "top-level"\n[xtable]\nalpha = "from-section"\n',
    )
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    monkeypatch.delenv("PIPEFY_X_ALPHA", raising=False)
    assert _PrefixedReader().alpha == "from-section"


def test_base_settings_strips_surrounding_whitespace_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Trimming env values is a boundary concern owned here, not in the library
    # value objects. A trailing newline (from ``$(...)``) or a padded value
    # is normalized as it is read.
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("PIPEFY_X_ALPHA", "  spaced \n")
    assert _PrefixedReader().alpha == "spaced"


def test_base_settings_strips_surrounding_whitespace_from_toml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_config(tmp_path / "config.toml", '[xtable]\nalpha = "  padded  "\n')
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    monkeypatch.delenv("PIPEFY_X_ALPHA", raising=False)
    assert _PrefixedReader().alpha == "padded"
