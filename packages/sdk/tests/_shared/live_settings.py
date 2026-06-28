"""Live Pipefy credentials helpers for SDK integration tests (no MCP imports)."""

from __future__ import annotations

import pytest
from httpx import Auth
from pipefy_auth import AuthSettings, missing_auth_message, resolve_pipefy_auth
from pipefy_infra.deployment import DeploymentConfig
from pipefy_infra.settings_base import PipefyBaseSettings

# These test readers stand in for the application edge (pipefy_cli / pipefy_mcp),
# which is the one layer allowed to read env. The library SRC ban on
# pydantic_settings does not apply to this test-only edge stand-in.
from pydantic_settings import SettingsConfigDict  # noqa: TID251

from pipefy_sdk.settings import SdkConfig

_MISSING_CREDS_MESSAGE = (
    "Pipefy credentials not configured: set PIPEFY_BASE_URL to your "
    "Pipefy API host (or leave unset for prod); " + missing_auth_message()
)


class _DeploymentEnv(DeploymentConfig, PipefyBaseSettings):
    """Test-only env reader for the deployment values (mirrors the app edge)."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")


class _SdkEnv(SdkConfig, PipefyBaseSettings):
    """Test-only env reader for the SDK knobs; ``deployment`` is injected."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")


def live_pipefy_settings() -> SdkConfig:
    """Load ``SdkConfig`` from the process environment and optional ``.env`` file."""
    return _SdkEnv(deployment=_DeploymentEnv())


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
    """Return True when a Pipefy host and a resolvable auth tier are both configured."""
    # ``PipefySettings.base_url`` carries a prod default; consulting the
    # resolved field would flip live tests on for every dev machine that
    # has *any* auth tier configured. Gate on the env var instead so live
    # tests stay opt-in.
    import os

    has_url = bool(os.environ.get("PIPEFY_BASE_URL", "").strip())
    return has_url and _try_resolve_live_auth() is not None


def require_live_creds() -> None:
    """Skip the current test if live credentials are not configured."""
    if not pipefy_live_configured():
        pytest.skip(_MISSING_CREDS_MESSAGE)
