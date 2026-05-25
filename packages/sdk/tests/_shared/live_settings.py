"""Live Pipefy credentials helpers for SDK integration tests (no MCP imports)."""

from __future__ import annotations

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
    # Intentionally omit ``oidc_client``: live integration tests must authenticate
    # via a service account or static bearer, never via a developer's personal
    # stored OAuth session. After PIPEFY_AUTH_URL gained a default value, a stray
    # ``pipefy auth login`` run on a developer machine would otherwise opt that
    # developer's tests into the stored-session tier and fire real traffic against
    # the prod Pipefy API under a personal user account.
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
    p = _resolved_pipefy()
    has_url = bool(
        p.graphql_url and str(p.graphql_url).startswith(("http://", "https://"))
    )
    return has_url and _try_resolve_live_auth() is not None


def require_live_creds() -> None:
    """Skip the current test if live credentials are not configured."""
    if not pipefy_live_configured():
        pytest.skip(_MISSING_CREDS_MESSAGE)
