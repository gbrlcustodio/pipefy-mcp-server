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


class _ClientEnv(PipefyBaseSettings):
    """Reads the ``PIPEFY_*`` SDK-client knobs from env / ``.env`` / TOML.

    A dumb env reader, not a value object: it imports no domain type and runs no
    SSRF / shape gate. Every field is optional and loosely typed so unset keys
    fall through and domain normalization (URL sanitizing, the keychain-backend
    lowering) stays on the value object the caller builds from
    :func:`read_client_env`.
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")

    base_url: str | None = Field(default=None)
    allow_insecure_urls: bool | None = Field(
        default=None, validation_alias=AliasChoices("PIPEFY_ALLOW_INSECURE_URLS")
    )
    gql_reuse_fetched_graphql_schema: bool | None = Field(default=None)
    default_webhook_name: str | None = Field(default=None)


class _AuthEnv(PipefyBaseSettings):
    """Reads the ``PIPEFY_AUTH_*`` knobs (plus the canonical credential aliases).

    Same contract as :class:`_ClientEnv`: a loosely-typed env reader, no domain
    import, no validation. ``base_url`` and ``allow_insecure_urls`` are absent on
    purpose: the caller injects the deployment-derived OAuth token URL and the
    shared insecure-URL posture into the auth value object rather than reading
    them here, so the host root is read once (via :func:`read_client_env`).
    """

    model_config = SettingsConfigDict(env_prefix="PIPEFY_AUTH_")

    issuer_url: str | None = Field(default=None)
    client_id: str | None = Field(default=None)
    disable_stored_session: bool | None = Field(default=None)
    keychain_backend: str | None = Field(default=None)
    static_token: str | None = Field(
        default=None, validation_alias=AliasChoices("PIPEFY_TOKEN")
    )
    service_account_client_id: str | None = Field(
        default=None, validation_alias=AliasChoices("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID")
    )
    service_account_client_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET"),
    )


def read_client_env(
    *, base_url: str | None = None, allow_insecure: bool | None = None
) -> dict[str, Any]:
    """Read the ``PIPEFY_*`` client knobs, flags overriding env, as a raw mapping.

    Returns only the keys an operator actually set (``exclude_unset``) so the
    value object the caller constructs (``pipefy_sdk.ClientSettings``) supplies
    every default in one place. ``base_url`` / ``allow_insecure`` are the CLI
    flag overrides; passing ``None`` leaves the env / file value (or the value
    object's default) in force. This is the single point where ``--base-url`` is
    applied.
    """
    overrides: dict[str, Any] = {}
    if base_url is not None:
        overrides["base_url"] = base_url.strip()
    if allow_insecure is not None:
        overrides["allow_insecure_urls"] = allow_insecure
    return _ClientEnv(**overrides).model_dump(exclude_unset=True)


def read_auth_env() -> dict[str, Any]:
    """Read the ``PIPEFY_AUTH_*`` knobs (and the credential aliases) as a raw mapping.

    Returns only operator-set keys (``exclude_unset``); ``pipefy_auth.AuthSettings``
    supplies the defaults. The deployment-derived ``service_account_token_url`` and
    ``allow_insecure_urls`` are injected by the caller, not read here.
    """
    return _AuthEnv().model_dump(exclude_unset=True)


__all__ = [
    "PipefyBaseSettings",
    "PipefyTomlConfigSource",
    "config_dir",
    "config_file_path",
    "read_auth_env",
    "read_client_env",
]
