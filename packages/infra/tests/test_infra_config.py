"""Tests for ``pipefy_infra.config`` (path discovery + TOML source)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipefy_infra.config import (
    PipefyBaseSettings,
    PipefyTomlConfigSource,
    config_dir,
    config_file_path,
)


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


class _PrefixedSettings(PipefyBaseSettings):
    model_config = SettingsConfigDict(env_prefix="PIPEFY_SAMPLE_")

    alpha: str = Field(default="default-alpha")


class _PrefixedInsecure(PipefyBaseSettings):
    # Mirrors the shared-flag pattern (a cross-cutting field pinned to one
    # canonical env var via an explicit alias) on top of the prefix-isolating
    # base, exercising _AliasOwnsEnvNameMixin under a non-matching prefix.
    model_config = SettingsConfigDict(env_prefix="PIPEFY_SAMPLE_")

    allow_insecure_urls: bool = Field(
        default=False,
        validation_alias=AliasChoices("PIPEFY_ALLOW_INSECURE_URLS"),
    )


def test_base_subclass_merges_config_keys() -> None:
    # A subclass declares only its prefix; the shared keys merge along the MRO.
    config = _PrefixedSettings.model_config
    assert config["env_prefix"] == "PIPEFY_SAMPLE_"
    assert config["extra"] == "ignore"
    assert config["populate_by_name"] is True


def test_base_subclass_inherits_toml_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # No per-class settings_customise_sources: TOML is wired in by the base.
    path = _write_config(tmp_path / "config.toml", 'alpha = "from-toml"\n')
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    monkeypatch.delenv("PIPEFY_SAMPLE_ALPHA", raising=False)
    assert _PrefixedSettings().alpha == "from-toml"


def test_base_subclass_env_overrides_toml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_config(tmp_path / "config.toml", 'alpha = "from-toml"\n')
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(path))
    monkeypatch.setenv("PIPEFY_SAMPLE_ALPHA", "from-env")
    assert _PrefixedSettings().alpha == "from-env"


def test_insecure_flag_reads_shared_var_under_any_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The alias outranks the subclass prefix: not PIPEFY_SAMPLE_ALLOW_INSECURE_URLS.
    monkeypatch.delenv("PIPEFY_SAMPLE_ALLOW_INSECURE_URLS", raising=False)
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "true")
    assert _PrefixedInsecure().allow_insecure_urls is True


def test_insecure_flag_defaults_false_and_accepts_name_kwarg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PIPEFY_ALLOW_INSECURE_URLS", raising=False)
    assert _PrefixedInsecure().allow_insecure_urls is False
    # populate_by_name lets field-name kwargs win despite the validation_alias.
    assert _PrefixedInsecure(allow_insecure_urls=True).allow_insecure_urls is True


def test_insecure_flag_ignores_prefixed_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The prefixed form must NOT set the shared field: the validation_alias is its
    # sole env name, so PIPEFY_SAMPLE_ALLOW_INSECURE_URLS is inert and only
    # PIPEFY_ALLOW_INSECURE_URLS controls the posture.
    monkeypatch.delenv("PIPEFY_ALLOW_INSECURE_URLS", raising=False)
    monkeypatch.setenv("PIPEFY_SAMPLE_ALLOW_INSECURE_URLS", "true")
    assert _PrefixedInsecure().allow_insecure_urls is False


def test_explicit_alias_is_the_sole_env_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A field with a validation_alias is read only through that alias, never via
    # the subclass prefix + field name (which populate_by_name would otherwise
    # accept). Pin the rule the mixin enforces on an arbitrary aliased field.
    class _Aliased(PipefyBaseSettings):
        model_config = SettingsConfigDict(env_prefix="PIPEFY_SAMPLE_")

        token: str | None = Field(
            default=None, validation_alias=AliasChoices("PIPEFY_CANONICAL_TOKEN")
        )

    monkeypatch.setenv("PIPEFY_CANONICAL_TOKEN", "canonical")
    monkeypatch.setenv("PIPEFY_SAMPLE_TOKEN", "shadow")
    assert _Aliased().token == "canonical"
