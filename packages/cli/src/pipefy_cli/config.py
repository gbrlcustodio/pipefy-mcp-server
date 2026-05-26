"""Resolve Pipefy + auth settings for the CLI (aligned with MCP ``PIPEFY_*`` keys).

Precedence is pure pydantic-settings: init kwargs (CLI flags) > env > ``.env``
> defaults. No TOML; operators wanting persistent global creds use shell rc
files or a system-wide ``.env``.
"""

from __future__ import annotations

from typing import Any

from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class CliSettings(BaseSettings):
    """Load ``PIPEFY_*`` from env / ``.env``."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    pipefy: PipefySettings = Field(default_factory=PipefySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)


def resolve_cli_settings(
    *,
    base_url_flag: str | None,
    allow_insecure_urls_flag: bool | None,
) -> CliSettings:
    """Resolve :class:`CliSettings` honoring CLI flags as init kwargs.

    Flags become init kwargs on the nested models, which pydantic-settings
    ranks above the env source. Auth-side values for fields with explicit
    ``AliasChoices`` (``base_url``, ``allow_insecure_urls``) are keyed by the
    alias name so they beat the nested ``AuthSettings`` env source — see
    :class:`pipefy_auth.AuthSettings` for the field aliases.

    Raises:
        ValueError: When validation fails (e.g. SSRF guard); message is user-facing.
    """
    pipefy_init: dict[str, Any] = {}
    auth_init: dict[str, Any] = {}
    if base_url_flag:
        stripped = base_url_flag.strip()
        pipefy_init["base_url"] = stripped
        auth_init["PIPEFY_BASE_URL"] = stripped
    if allow_insecure_urls_flag is not None:
        pipefy_init["allow_insecure_urls"] = allow_insecure_urls_flag
        auth_init["PIPEFY_ALLOW_INSECURE_URLS"] = allow_insecure_urls_flag

    init_kwargs: dict[str, Any] = {}
    if pipefy_init:
        init_kwargs["pipefy"] = pipefy_init
    if auth_init:
        init_kwargs["auth"] = auth_init

    try:
        return CliSettings(**init_kwargs)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


__all__ = ["CliSettings", "resolve_cli_settings"]
