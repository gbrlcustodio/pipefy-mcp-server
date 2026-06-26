"""Resolve Pipefy + auth settings for the CLI (aligned with MCP ``PIPEFY_*`` keys).

Precedence is pure pydantic-settings: init kwargs (CLI flags) > env > ``.env``
> defaults. No TOML; operators wanting persistent global creds use shell rc
files or a system-wide ``.env``.

The composition deliberately does NOT use ``env_nested_delimiter``: that flag
splits any matching env var (e.g. ``AUTH_BASE_URL``) into a nested-field path,
which would let unprefixed env vars bypass each nested model's own env-prefix
gate (``PIPEFY_`` for the SDK, ``PIPEFY_AUTH_`` for auth). Each nested model
loads its env independently.
"""

from __future__ import annotations

from typing import Any

from pipefy_auth import AuthSettings
from pipefy_sdk import ClientSettings
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class CliSettings(BaseSettings):
    """Composes :class:`ClientSettings` + :class:`AuthSettings` for CLI use."""

    model_config = SettingsConfigDict(extra="ignore")

    sdk: ClientSettings = Field(default_factory=ClientSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)


def resolve_cli_settings(
    *,
    base_url_flag: str | None,
    allow_insecure_urls_flag: bool | None,
) -> CliSettings:
    """Resolve :class:`CliSettings` honoring CLI flags as init kwargs.

    Flags become init kwargs on each nested model's own source chain, where they
    outrank env. ``base_url`` and ``allow_insecure_urls`` carry explicit
    ``AliasChoices`` (``PIPEFY_BASE_URL`` / ``PIPEFY_ALLOW_INSECURE_URLS``), but
    ``populate_by_name=True`` still lets these field-name kwargs win.

    Raises:
        ValueError: When validation fails (e.g. SSRF guard); message is user-facing.
    """
    pipefy_init: dict[str, Any] = {}
    auth_init: dict[str, Any] = {}
    if base_url_flag is not None:
        stripped = base_url_flag.strip()
        pipefy_init["base_url"] = stripped
        auth_init["base_url"] = stripped
    if allow_insecure_urls_flag is not None:
        pipefy_init["allow_insecure_urls"] = allow_insecure_urls_flag
        auth_init["allow_insecure_urls"] = allow_insecure_urls_flag

    try:
        return CliSettings(
            sdk=ClientSettings(**pipefy_init),
            auth=AuthSettings(**auth_init),
        )
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


__all__ = ["CliSettings", "resolve_cli_settings"]
