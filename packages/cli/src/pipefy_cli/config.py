"""Resolve Pipefy settings for the CLI (aligned with MCP ``PIPEFY_*`` keys)."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any, Self

from pipefy_sdk import PipefySettings
from pipefy_sdk.utils.url_ssrf import validate_https_service_endpoint_url
from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipefy_cli._docs import DOCS_SETUP_REF

_ALLOW_INSECURE_ENV_KEY = "PIPEFY_ALLOW_INSECURE_URLS"

USER_CONFIG_PATH = Path.home() / ".config/pipefy/config.toml"

# Legacy ``[pipefy]`` TOML keys mapped to their replacements (mirrors the
# ``PIPEFY_OAUTH_*`` → ``PIPEFY_SERVICE_ACCOUNT_*`` env-var rename in #127).
_LEGACY_TOML_KEYS_TO_NEW: dict[str, str] = {
    "oauth_url": "service_account_url",
    "oauth_client": "service_account_client_id",
    "oauth_secret": "service_account_client_secret",
}

_warned_legacy_toml_keys: set[str] = set()


def _warn_once_for_legacy_toml_key(legacy_key: str, new_key: str) -> None:
    if legacy_key in _warned_legacy_toml_keys:
        return
    sys.stderr.write(
        f"warning: '{legacy_key}' in {USER_CONFIG_PATH} is deprecated; "
        f"rename to '{new_key}'. The legacy key will be removed in a future beta.\n"
    )
    _warned_legacy_toml_keys.add(legacy_key)


def _reset_legacy_toml_warning_state() -> None:
    """Test helper: clear the one-shot dedup so a fixture can re-trigger the warning."""
    _warned_legacy_toml_keys.clear()


DEFAULT_AUTH_CLIENT_ID = "pipefy-cli"


class CliSettings(BaseSettings):
    """Load ``PIPEFY_*`` from the environment and ``.env`` in the working directory."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    pipefy: PipefySettings = Field(default_factory=PipefySettings)
    auth_url: str | None = Field(default=None, alias="PIPEFY_AUTH_URL")
    auth_client_id: str = Field(
        default=DEFAULT_AUTH_CLIENT_ID, alias="PIPEFY_AUTH_CLIENT_ID"
    )

    @model_validator(mode="after")
    def _validate_auth_url(self) -> Self:
        if self.auth_url is not None and (u := self.auth_url.strip()):
            validate_https_service_endpoint_url(
                u, "auth_url", allow_insecure=self.pipefy.allow_insecure_urls
            )
        return self


def _revalidate(pipefy: PipefySettings, patch: dict[str, Any]) -> PipefySettings:
    """Merge ``patch`` and re-validate (``model_copy`` would skip URL validators)."""
    if not patch:
        return pipefy
    merged = {**pipefy.model_dump(), **patch}
    return PipefySettings.model_validate(merged)


def _read_toml_pipefy_dict() -> dict[str, Any]:
    """Return the ``[pipefy]`` table (or top-level keys) from the user config file."""
    if not USER_CONFIG_PATH.is_file():
        return {}
    try:
        raw = USER_CONFIG_PATH.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        msg = (
            f"Could not read Pipefy config file at {USER_CONFIG_PATH}: {exc}. "
            f"See {DOCS_SETUP_REF} for the expected format."
        )
        raise ValueError(msg) from exc
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


def _fill_if_missing_str(
    pipefy: PipefySettings,
    blob: dict[str, Any],
    field: str,
    key: str,
    patch: dict[str, Any],
) -> None:
    if _is_missing(getattr(pipefy, field)) and blob.get(key):
        patch[field] = str(blob[key]).strip()


def _normalize_legacy_toml_keys(blob: dict[str, Any]) -> dict[str, Any]:
    """Translate legacy ``oauth_*`` TOML keys to ``service_account_*``; warn once per legacy key.

    When both keys are present, the new key wins (mirrors ``AliasChoices`` precedence).
    """
    for legacy, new in _LEGACY_TOML_KEYS_TO_NEW.items():
        if legacy in blob:
            _warn_once_for_legacy_toml_key(legacy, new)
            if new not in blob:
                blob[new] = blob[legacy]
    return blob


def apply_toml_fallback(pipefy: PipefySettings) -> PipefySettings:
    """Fill only attributes still unset after env / ``.env`` (lowest precedence)."""
    blob = _read_toml_pipefy_dict()
    if not blob:
        return pipefy
    blob = _normalize_legacy_toml_keys(blob)
    patch: dict[str, Any] = {}
    _fill_if_missing_str(pipefy, blob, "graphql_url", "graphql_url", patch)
    _fill_if_missing_str(pipefy, blob, "internal_api_url", "internal_api_url", patch)
    _fill_if_missing_str(
        pipefy, blob, "service_account_url", "service_account_url", patch
    )
    _fill_if_missing_str(
        pipefy, blob, "service_account_client_id", "service_account_client_id", patch
    )
    _fill_if_missing_str(
        pipefy,
        blob,
        "service_account_client_secret",
        "service_account_client_secret",
        patch,
    )
    if blob.get("service_account_ids") is not None and not pipefy.service_account_ids:
        patch["service_account_ids"] = blob["service_account_ids"]
    if blob.get("allow_insecure_urls") is not None and not pipefy.allow_insecure_urls:
        patch["allow_insecure_urls"] = bool(blob["allow_insecure_urls"])
    return _revalidate(pipefy, patch)


def resolve_cli_settings(
    *,
    graphql_url_flag: str | None,
    allow_insecure_urls_flag: bool | None,
) -> CliSettings:
    """Resolve the full :class:`CliSettings`: env, ``.env``, TOML fallback, then flags.

    Returns a single ``CliSettings`` instance with the nested ``.pipefy`` field
    fully resolved (TOML + flag overrides applied) and the top-level auth fields
    (``auth_url``, ``auth_client_id``) populated from env / ``.env``.

    Raises:
        ValueError: When validation fails (e.g. SSRF guard); message is user-facing.
    """
    prev_allow = os.environ.get(_ALLOW_INSECURE_ENV_KEY)
    if allow_insecure_urls_flag is True:
        os.environ[_ALLOW_INSECURE_ENV_KEY] = "true"
    try:
        cli = CliSettings()
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    finally:
        if allow_insecure_urls_flag is True:
            if prev_allow is None:
                os.environ.pop(_ALLOW_INSECURE_ENV_KEY, None)
            else:
                os.environ[_ALLOW_INSECURE_ENV_KEY] = prev_allow

    try:
        pipefy = apply_toml_fallback(cli.pipefy)
        patch: dict[str, Any] = {}
        if graphql_url_flag:
            patch["graphql_url"] = graphql_url_flag.strip()
        if allow_insecure_urls_flag is not None:
            patch["allow_insecure_urls"] = allow_insecure_urls_flag
        pipefy = _revalidate(pipefy, patch)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    return cli.model_copy(update={"pipefy": pipefy})


def ensure_public_graphql_configured(pipefy: PipefySettings) -> None:
    """Ensure GraphQL URL is present before building a client.

    Raises:
        ValueError: With pointer to ``docs/setup.md``.
    """
    if _is_missing(pipefy.graphql_url):
        msg = (
            "PIPEFY_GRAPHQL_URL is required (or pass --graphql-url). "
            f"See {DOCS_SETUP_REF} for environment variables."
        )
        raise ValueError(msg)


def describe_missing_service_account_vars(pipefy: PipefySettings) -> str:
    """Return a short message listing missing service-account credential variables."""
    missing: list[str] = []
    if _is_missing(pipefy.service_account_url):
        missing.append("PIPEFY_SERVICE_ACCOUNT_URL")
    if _is_missing(pipefy.service_account_client_id):
        missing.append("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID")
    if _is_missing(pipefy.service_account_client_secret):
        missing.append("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET")
    return ", ".join(missing)


__all__ = [
    "CliSettings",
    "DEFAULT_AUTH_CLIENT_ID",
    "USER_CONFIG_PATH",
    "apply_toml_fallback",
    "describe_missing_service_account_vars",
    "ensure_public_graphql_configured",
    "resolve_cli_settings",
]
