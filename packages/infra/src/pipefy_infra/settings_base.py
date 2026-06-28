"""Shared ``pydantic-settings`` base for the application-edge env readers.

The applications (``pipefy_cli``, ``pipefy_mcp``) own all env reading. Each
concept's reader subclasses :class:`PipefyBaseSettings`, which owns the one
source-precedence chain (init > env > dotenv > config.toml > defaults) and the
shared :class:`~pydantic_settings.SettingsConfigDict` defaults, so a reader shell
only declares its ``env_prefix`` (and, for sectioned TOML, its
``_toml_section``).

This is generic machinery: it imports only ``pydantic-settings`` and the
:class:`~pipefy_infra.config.PipefyTomlConfigSource`, never the SDK / auth value
models, so ``pipefy_infra`` stays a leaf package.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from pipefy_infra.config import PipefyTomlConfigSource


class PipefyBaseSettings(BaseSettings):
    """Base for app-edge env readers: owns the source chain and shared config.

    Subclasses set ``model_config = SettingsConfigDict(env_prefix="PIPEFY_X_")``
    (merged with the defaults here) and, when their TOML keys live under a
    sub-table rather than the top level, override :attr:`_toml_section`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # TOML sub-table this reader's keys live under. ``None`` reads top-level
    # keys (today's behaviour). Set on readers whose bare field names would
    # otherwise collide across concepts in one flat TOML namespace.
    _toml_section: ClassVar[str | None] = None

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
        # TOML keys are bare pydantic field names; the env prefix and any
        # env-only ``AliasChoices`` do not apply to TOML lookups.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            PipefyTomlConfigSource(settings_cls, section=cls._toml_section),
            file_secret_settings,
        )


__all__ = ["PipefyBaseSettings"]
