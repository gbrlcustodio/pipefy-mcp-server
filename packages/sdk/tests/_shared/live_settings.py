"""Live Pipefy credentials helpers for SDK integration tests (no MCP imports)."""

from __future__ import annotations

import os

import pytest
from httpx import Auth
from pipefy_auth import AuthSettings, missing_auth_message, resolve_pipefy_auth
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipefy_sdk.settings import PipefySettings

_MISSING_CREDS_MESSAGE = (
    "Pipefy credentials not configured: PIPEFY_GRAPHQL_URL required; "
    + missing_auth_message()
)


class _LiveEnvSettings(BaseSettings):
    """Minimal env loader mirroring MCP nested PIPEFY_* layout."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    pipefy: PipefySettings = Field(default_factory=PipefySettings)


def _resolved_pipefy() -> PipefySettings:
    return _LiveEnvSettings().pipefy


def live_pipefy_settings() -> PipefySettings:
    """Load ``PipefySettings`` from the process environment and optional ``.env`` file."""
    return _resolved_pipefy()


def live_auth_settings() -> AuthSettings:
    """Load ``AuthSettings`` from the process environment and optional ``.env`` file."""
    return AuthSettings()


def _try_resolve_live_auth() -> Auth | None:
    a = live_auth_settings()
    # ``oidc_client=None``: a stray ``pipefy auth login`` on a dev machine would
    # otherwise satisfy live-creds detection via the developer's personal session.
    return resolve_pipefy_auth(
        static_token=a.static_token,
        service_account=a.to_service_account(),
        oidc_client=None,
    )


def live_resolved_auth() -> Auth:
    """Resolve a live ``httpx.Auth`` via the production precedence chain, or skip the test."""
    resolved = _try_resolve_live_auth()
    if resolved is None:
        pytest.skip(_MISSING_CREDS_MESSAGE)
    return resolved


def pipefy_live_configured() -> bool:
    """Return True when GraphQL URL plus a resolvable auth tier is configured.

    Auth detection delegates to :func:`pipefy_auth.resolve_pipefy_auth` so a
    setup that names a stored-session tier but has no keychain entry is
    reported as unconfigured (matches what ``live_resolved_auth`` would do).
    """
    # ``PipefySettings.graphql_url`` now defaults to the Pipefy production
    # endpoint; consulting the resolved field would flip live tests on for
    # every dev machine that has *any* auth tier configured. Gate on the env
    # var instead so live tests stay opt-in (mirrors how ``_try_resolve_live_auth``
    # ignores the stored-session tier).
    has_url = bool(os.environ.get("PIPEFY_GRAPHQL_URL", "").strip())
    return has_url and _try_resolve_live_auth() is not None


def require_live_creds() -> None:
    """Skip the current test if live credentials are not configured."""
    if not pipefy_live_configured():
        pytest.skip(_MISSING_CREDS_MESSAGE)
