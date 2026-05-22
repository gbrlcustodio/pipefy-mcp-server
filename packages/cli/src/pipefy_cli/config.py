"""Resolve Pipefy + auth settings for the CLI (aligned with MCP ``PIPEFY_*`` keys)."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any, Self

from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings
from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipefy_cli._docs import DOCS_SETUP_REF

_ALLOW_INSECURE_ENV_KEY = "PIPEFY_ALLOW_INSECURE_URLS"

USER_CONFIG_PATH = Path.home() / ".config/pipefy/config.toml"

_LEGACY_TOML_KEYS_TO_NEW: dict[str, str] = {
    "oauth_url": "service_account_url",
    "oauth_client": "service_account_client_id",
    "oauth_secret": "service_account_client_secret",
}

# Keys recognised under ``[pipefy]`` that belong to auth, not the SDK. Used by
# the TOML loader to route values into ``AuthSettings`` instead of
# ``PipefySettings``.
_AUTH_TOML_KEYS: frozenset[str] = frozenset(
    {
        "service_account_url",
        "service_account_client_id",
        "service_account_client_secret",
        "auth_url",
        "auth_client_id",
    }
)

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
    auth: AuthSettings = Field(default_factory=AuthSettings)

    @model_validator(mode="after")
    def _validate_auth_urls(self) -> Self:
        self.auth.validate_urls(allow_insecure=self.pipefy.allow_insecure_urls)
        return self


def _revalidate_pipefy(pipefy: PipefySettings, patch: dict[str, Any]) -> PipefySettings:
    """Merge ``patch`` and re-validate (``model_copy`` would skip URL validators)."""
    if not patch:
        return pipefy
    merged = {**pipefy.model_dump(), **patch}
    return PipefySettings.model_validate(merged)


def _revalidate_auth(
    auth: AuthSettings, patch: dict[str, Any], *, allow_insecure: bool
) -> AuthSettings:
    if not patch:
        return auth
    merged = {**auth.model_dump(), **patch}
    fresh = AuthSettings.model_validate(merged)
    fresh.validate_urls(allow_insecure=allow_insecure)
    return fresh


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


def _normalize_legacy_toml_keys(blob: dict[str, Any]) -> dict[str, Any]:
    """Translate legacy ``oauth_*`` TOML keys to ``service_account_*``; warn once per legacy key."""
    if not any(legacy in blob for legacy in _LEGACY_TOML_KEYS_TO_NEW):
        return blob
    for legacy, new in _LEGACY_TOML_KEYS_TO_NEW.items():
        if legacy in blob:
            _warn_once_for_legacy_toml_key(legacy, new)
            if new not in blob:
                blob[new] = blob[legacy]
    return blob


def _fill_if_missing_str(
    model: PipefySettings | AuthSettings,
    blob: dict[str, Any],
    field: str,
    key: str,
    patch: dict[str, Any],
) -> None:
    if _is_missing(getattr(model, field)) and blob.get(key):
        patch[field] = str(blob[key]).strip()


def apply_toml_fallback(
    pipefy: PipefySettings, auth: AuthSettings
) -> tuple[PipefySettings, AuthSettings]:
    """Fill attributes still unset after env / ``.env`` from the user TOML file (lowest precedence)."""
    blob = _read_toml_pipefy_dict()
    if not blob:
        return pipefy, auth
    blob = _normalize_legacy_toml_keys(blob)

    pipefy_patch: dict[str, Any] = {}
    _fill_if_missing_str(pipefy, blob, "graphql_url", "graphql_url", pipefy_patch)
    _fill_if_missing_str(
        pipefy, blob, "internal_api_url", "internal_api_url", pipefy_patch
    )
    if blob.get("service_account_ids") is not None and not pipefy.service_account_ids:
        pipefy_patch["service_account_ids"] = blob["service_account_ids"]
    if blob.get("allow_insecure_urls") is not None and not pipefy.allow_insecure_urls:
        pipefy_patch["allow_insecure_urls"] = bool(blob["allow_insecure_urls"])

    auth_patch: dict[str, Any] = {}
    for key in _AUTH_TOML_KEYS:
        _fill_if_missing_str(auth, blob, key, key, auth_patch)

    new_pipefy = _revalidate_pipefy(pipefy, pipefy_patch)
    new_auth = _revalidate_auth(
        auth, auth_patch, allow_insecure=new_pipefy.allow_insecure_urls
    )
    return new_pipefy, new_auth


def resolve_cli_settings(
    *,
    graphql_url_flag: str | None,
    allow_insecure_urls_flag: bool | None,
) -> CliSettings:
    """Resolve the full :class:`CliSettings`: env, ``.env``, TOML fallback, then flags.

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
        pipefy, auth = apply_toml_fallback(cli.pipefy, cli.auth)
        pipefy_patch: dict[str, Any] = {}
        if graphql_url_flag:
            pipefy_patch["graphql_url"] = graphql_url_flag.strip()
        if allow_insecure_urls_flag is not None:
            pipefy_patch["allow_insecure_urls"] = allow_insecure_urls_flag
        pipefy = _revalidate_pipefy(pipefy, pipefy_patch)
        # Re-validate auth URLs against the (possibly newly-flipped) allow_insecure_urls.
        auth.validate_urls(allow_insecure=pipefy.allow_insecure_urls)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    return cli.model_copy(update={"pipefy": pipefy, "auth": auth})


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


__all__ = [
    "CliSettings",
    "USER_CONFIG_PATH",
    "apply_toml_fallback",
    "ensure_public_graphql_configured",
    "resolve_cli_settings",
]
