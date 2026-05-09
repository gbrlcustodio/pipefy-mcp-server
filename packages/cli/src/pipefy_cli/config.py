"""Resolve Pipefy settings for the CLI (aligned with MCP ``PIPEFY_*`` keys)."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pipefy_sdk import PipefySettings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DOCS_SETUP_REF = "docs/setup.md"

_ALLOW_INSECURE_ENV_KEY = "PIPEFY_ALLOW_INSECURE_URLS"

USER_CONFIG_PATH = Path.home() / ".config/pipefy/config.toml"


class CliSettings(BaseSettings):
    """Load ``PIPEFY_*`` from the environment and ``.env`` in the working directory."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    pipefy: PipefySettings = Field(default_factory=PipefySettings)


def _read_toml_pipefy_dict() -> dict[str, Any]:
    """Return the ``[pipefy]`` table (or top-level keys) from the user config file."""
    if not USER_CONFIG_PATH.is_file():
        return {}
    raw = USER_CONFIG_PATH.read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    section = data.get("pipefy")
    if isinstance(section, dict):
        return dict(section)
    return dict(data)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def apply_toml_fallback(pipefy: PipefySettings) -> PipefySettings:
    """Fill only attributes still unset after env / ``.env`` (lowest precedence)."""
    blob = _read_toml_pipefy_dict()
    if not blob:
        return pipefy
    patch: dict[str, Any] = {}
    if _is_missing(pipefy.graphql_url) and blob.get("graphql_url"):
        patch["graphql_url"] = str(blob["graphql_url"]).strip()
    if _is_missing(pipefy.internal_api_url) and blob.get("internal_api_url"):
        patch["internal_api_url"] = str(blob["internal_api_url"]).strip()
    if _is_missing(pipefy.oauth_url) and blob.get("oauth_url"):
        patch["oauth_url"] = str(blob["oauth_url"]).strip()
    if _is_missing(pipefy.oauth_client) and blob.get("oauth_client"):
        patch["oauth_client"] = str(blob["oauth_client"]).strip()
    if _is_missing(pipefy.oauth_secret) and blob.get("oauth_secret"):
        patch["oauth_secret"] = str(blob["oauth_secret"]).strip()
    if blob.get("service_account_ids") is not None and not pipefy.service_account_ids:
        patch["service_account_ids"] = blob["service_account_ids"]
    if blob.get("allow_insecure_urls") is not None and not pipefy.allow_insecure_urls:
        patch["allow_insecure_urls"] = bool(blob["allow_insecure_urls"])
    return pipefy.model_copy(update=patch) if patch else pipefy


def resolve_pipefy_settings(
    *,
    graphql_url_flag: str | None,
    allow_insecure_urls_flag: bool | None,
) -> PipefySettings:
    """Merge env, ``.env``, optional user TOML, then CLI flags (flags win).

    Args:
        graphql_url_flag: When set, overrides ``PIPEFY_GRAPHQL_URL`` / file values.
        allow_insecure_urls_flag: When not ``None``, overrides insecure URL policy.

    Returns:
        Validated :class:`PipefySettings` (same shape as MCP ``settings.pipefy``).

    Raises:
        ValueError: When validation fails (e.g. SSRF guard); message is user-facing.
    """
    # Apply `--allow-insecure-urls` before constructing settings so ``PipefySettings``
    # URL validation sees the effective policy (matches MCP SSRF rules).
    prev_allow = os.environ.get(_ALLOW_INSECURE_ENV_KEY)
    if allow_insecure_urls_flag is True:
        os.environ[_ALLOW_INSECURE_ENV_KEY] = "true"
    try:
        pipefy = CliSettings().pipefy
    finally:
        if allow_insecure_urls_flag is True:
            if prev_allow is None:
                os.environ.pop(_ALLOW_INSECURE_ENV_KEY, None)
            else:
                os.environ[_ALLOW_INSECURE_ENV_KEY] = prev_allow

    pipefy = apply_toml_fallback(pipefy)

    patch: dict[str, Any] = {}
    if graphql_url_flag:
        patch["graphql_url"] = graphql_url_flag.strip()
    if allow_insecure_urls_flag is not None:
        patch["allow_insecure_urls"] = allow_insecure_urls_flag

    if patch:
        pipefy = pipefy.model_copy(update=patch)

    return pipefy


def ensure_public_graphql_configured(pipefy: PipefySettings) -> None:
    """Ensure GraphQL URL is present before building a client.

    Raises:
        ValueError: With pointer to ``docs/setup.md``.
    """
    if _is_missing(pipefy.graphql_url):
        msg = (
            "PIPEFY_GRAPHQL_URL is required (or pass --graphql-url). "
            f"See {_DOCS_SETUP_REF} for environment variables."
        )
        raise ValueError(msg)


def describe_missing_oauth_vars(pipefy: PipefySettings) -> str:
    """Return a short message listing missing OAuth-related variables."""
    missing: list[str] = []
    if _is_missing(pipefy.oauth_url):
        missing.append("PIPEFY_OAUTH_URL")
    if _is_missing(pipefy.oauth_client):
        missing.append("PIPEFY_OAUTH_CLIENT")
    if _is_missing(pipefy.oauth_secret):
        missing.append("PIPEFY_OAUTH_SECRET")
    return ", ".join(missing)


def runtime_config_summary_for_tests() -> dict[str, Any]:
    """Expose minimal env state for tests (no secrets)."""
    keys = (
        "PIPEFY_GRAPHQL_URL",
        "PIPEFY_INTERNAL_API_URL",
        "PIPEFY_OAUTH_URL",
        "PIPEFY_OAUTH_CLIENT",
        "PIPEFY_OAUTH_SECRET",
        "PIPEFY_ALLOW_INSECURE_URLS",
    )
    return {k: os.environ.get(k) for k in keys}


__all__ = [
    "CliSettings",
    "USER_CONFIG_PATH",
    "apply_toml_fallback",
    "describe_missing_oauth_vars",
    "ensure_public_graphql_configured",
    "resolve_pipefy_settings",
    "runtime_config_summary_for_tests",
]
