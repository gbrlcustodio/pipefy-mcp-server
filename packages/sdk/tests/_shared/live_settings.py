"""Live Pipefy credentials helpers for SDK integration tests (no MCP imports)."""

from __future__ import annotations

import pytest
from httpx import Auth
from pipefy_auth import AuthSettings, resolve_pipefy_auth
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipefy_sdk.settings import PipefySettings


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


def live_resolved_auth() -> Auth:
    """Resolve a live ``httpx.Auth`` via the production precedence chain, or skip the test."""
    a = live_auth_settings()
    resolved = resolve_pipefy_auth(
        static_token=a.static_token,
        service_account=a.to_service_account(),
        oidc_client=a.to_oidc_client(),
    )
    if resolved is None:
        pytest.skip(
            "No live Pipefy auth configured "
            "(set PIPEFY_TOKEN or PIPEFY_SERVICE_ACCOUNT_* in .env)"
        )
    return resolved


def pipefy_live_configured() -> bool:
    """Return True when GraphQL URL plus at least one auth tier is configured."""
    p = _resolved_pipefy()
    a = live_auth_settings()
    has_url = bool(
        p.graphql_url and str(p.graphql_url).startswith(("http://", "https://"))
    )
    has_auth = bool(
        (a.static_token and a.static_token.strip())
        or a.to_service_account() is not None
        or a.to_oidc_client() is not None
    )
    return has_url and has_auth


def require_live_creds() -> None:
    """Skip the current test if live credentials are not configured."""
    if not pipefy_live_configured():
        pytest.skip(
            "Pipefy credentials not configured "
            "(PIPEFY_GRAPHQL_URL plus PIPEFY_TOKEN or PIPEFY_SERVICE_ACCOUNT_* in .env)"
        )
