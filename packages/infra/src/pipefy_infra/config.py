"""Pipefy on-disk configuration: where it lives and how it's read.

Bounded context: the operator-editable Pipefy config file. Owns path
discovery (where the OS expects the config directory and the
``config.toml`` file to live) and the ``pydantic-settings`` source that
reads top-level TOML keys at settings construction.

Path discovery is intentionally hand-rolled. Adopting ``platformdirs``
would land config under ``~/Library/Application Support/pipefy`` on
macOS, breaking parity with the CLI tools operators expect to share that
location (``gh``, ``uv``, ``gcloud``).

The TOML source is schema-agnostic: it returns the full top-level mapping
filtered to the consuming ``BaseSettings`` subclass's field names
(env-only aliases like ``PIPEFY_TOKEN`` are intentionally not honoured as
TOML keys; operators get one canonical TOML schema).
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_CONFIG_FILE_ENV = "PIPEFY_CONFIG_FILE"


def config_dir() -> Path:
    """Resolve the shared Pipefy configuration directory.

    On POSIX honours ``XDG_CONFIG_HOME`` (per the XDG Base Directory
    Specification) and falls back to ``~/.config``. On Windows uses
    ``%APPDATA%`` with a ``~/AppData/Roaming`` fallback. Returns the path
    unconditionally; the directory may not yet exist.
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "pipefy"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "pipefy"


def config_file_path() -> Path:
    """Resolve the operator-editable ``config.toml`` path.

    Honours the ``PIPEFY_CONFIG_FILE`` env override (useful for tests, ops
    automation, and multi-environment workflows). Returns the path
    unconditionally; the file may not yet exist; consumers must tolerate that.
    """
    override = os.environ.get(_CONFIG_FILE_ENV)
    if override:
        return Path(override)
    return config_dir() / "config.toml"


class PipefyTomlConfigSource(PydanticBaseSettingsSource):
    """Load top-level TOML keys from :func:`config_file_path` as a settings source.

    Missing file produces an empty mapping (no error). Malformed TOML
    produces ``ValueError`` quoting the file path, chained from the
    original ``tomllib.TOMLDecodeError`` so the parser context is preserved.
    """

    _cache: dict[str, Any] | None = None

    def _data(self) -> dict[str, Any]:
        # Pydantic-settings constructs a fresh source per ``BaseSettings.__init__``,
        # so caching on the instance scopes to "one settings construction"; the
        # lazy behaviour the tests exercise (env change between constructions)
        # still works because each construction gets a new source instance.
        if self._cache is not None:
            return self._cache
        path = config_file_path()
        if not path.is_file():
            self._cache = {}
            return self._cache
        try:
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            msg = f"invalid TOML in {path}"
            raise ValueError(msg) from exc
        known = set(self.settings_cls.model_fields)
        self._cache = {key: value for key, value in raw.items() if key in known}
        return self._cache

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        del field  # signature dictated by ``PydanticBaseSettingsSource``
        data = self._data()
        if field_name in data:
            return data[field_name], field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._data()


class _AliasOwnsEnvNameMixin:
    """An explicit ``validation_alias`` is the only env name for its field.

    With ``populate_by_name=True``, pydantic-settings reads an aliased field from
    both its alias and the prefixed field name, so a cross-cutting field like
    ``allow_insecure_urls`` (alias ``PIPEFY_ALLOW_INSECURE_URLS``) would also load
    from the subclass-prefixed ``PIPEFY_JWT_ALLOW_INSECURE_URLS`` / ``PIPEFY_AUTH_…``,
    and the shared var would silently win on conflict. Reading such fields only
    through their alias keeps one canonical var in control regardless of the
    model's prefix.
    """

    def _extract_field_info(
        self, field: FieldInfo, field_name: str
    ) -> list[tuple[str, str, bool]]:
        infos = super()._extract_field_info(field, field_name)  # type: ignore[misc]
        if field.validation_alias is None:
            return infos
        # Alias candidates key on the alias string; the populate_by_name fallback
        # keys on the bare field name (the one that picks up the env prefix). Drop
        # only that fallback so the alias is the field's sole env source.
        return [info for info in infos if info[0] != field_name]


class _PipefyEnvSource(_AliasOwnsEnvNameMixin, EnvSettingsSource):
    pass


class _PipefyDotEnvSource(_AliasOwnsEnvNameMixin, DotEnvSettingsSource):
    pass


class PipefyBaseSettings(BaseSettings):
    """Shared base for every ``PIPEFY_*`` settings model across the packages.

    Carries the config and source chain each leaf model otherwise repeats:
    env + ``.env`` loading, ``extra="ignore"`` so foreign vars fall through the
    prefix gate rather than erroring, and ``populate_by_name=True`` so
    field-name kwargs work alongside per-field ``AliasChoices``. Subclasses set
    only their own ``env_prefix``; pydantic merges it onto these defaults along
    the MRO.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: init_kwargs > env > dotenv > config.toml > file_secret.
        # TOML keys are bare pydantic field names; neither the env prefix nor
        # the env-only AliasChoices apply to TOML lookups.
        #
        # The default env/dotenv sources are replaced with prefix-isolating ones
        # so a field's explicit validation_alias is its only env name (see
        # _AliasOwnsEnvNameMixin); the passed-in equivalents are discarded.
        del env_settings, dotenv_settings
        return (
            init_settings,
            _PipefyEnvSource(settings_cls),
            _PipefyDotEnvSource(settings_cls),
            PipefyTomlConfigSource(settings_cls),
            file_secret_settings,
        )


class InsecureUrlSettings(PipefyBaseSettings):
    """Base for settings models that gate their URLs behind one shared flag.

    Adds ``allow_insecure_urls``, read only from ``PIPEFY_ALLOW_INSECURE_URLS``;
    the subclass's ``env_prefix`` does not apply to it (the explicit alias is its
    sole env name, enforced by the prefix-isolating env source), so the whole
    deployment has a single insecure-URL posture rather than a per-model toggle.
    """

    allow_insecure_urls: bool = Field(
        default=False,
        validation_alias=AliasChoices("PIPEFY_ALLOW_INSECURE_URLS"),
        description=(
            "When true (env: PIPEFY_ALLOW_INSECURE_URLS), URLs may use http:// "
            "and internal hosts; local development only, do not enable in "
            "production."
        ),
    )


__all__ = [
    "InsecureUrlSettings",
    "PipefyBaseSettings",
    "PipefyTomlConfigSource",
    "config_dir",
    "config_file_path",
]
