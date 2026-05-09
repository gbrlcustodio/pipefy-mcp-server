"""Live Pipefy credentials helpers for SDK integration tests (no MCP imports)."""

from __future__ import annotations

import pytest
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


def pipefy_live_configured() -> bool:
    """Return True when all OAuth + GraphQL credentials are present."""
    p = _resolved_pipefy()
    return bool(
        p.graphql_url
        and str(p.graphql_url).startswith(("http://", "https://"))
        and p.oauth_url
        and str(p.oauth_url).startswith(("http://", "https://"))
        and p.oauth_client
        and p.oauth_secret
    )


def require_live_creds() -> None:
    """Skip the current test if live credentials are not configured."""
    if not pipefy_live_configured():
        pytest.skip(
            "Pipefy credentials not configured (PIPEFY_GRAPHQL_URL + OAuth in .env)"
        )
