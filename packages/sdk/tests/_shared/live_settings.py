"""Live Pipefy credentials helpers for SDK integration tests (no MCP imports)."""

from __future__ import annotations

import pytest
from httpx import Auth
from pipefy_auth import (
    AuthConfig,
    ServiceAccountCredentials,
    missing_auth_message,
    resolve_pipefy_auth,
)
from pipefy_infra.deployment import DeploymentConfig
from pipefy_infra.env import load_deployment
from pipefy_infra.settings_base import PipefyBaseSettings
from pydantic import AliasChoices, Field

# These test readers stand in for the application edge (pipefy_cli / pipefy_mcp),
# which is the one layer allowed to read env. The library SRC ban on
# pydantic_settings does not apply to this test-only edge stand-in.
from pydantic_settings import SettingsConfigDict  # noqa: TID251

from pipefy_sdk.config import SdkConfig
from pipefy_sdk.endpoints import PipefyEndpoints
from pipefy_sdk.env import load_sdk

_MISSING_CREDS_MESSAGE = (
    "Pipefy credentials not configured: set PIPEFY_BASE_URL to your "
    "Pipefy API host (or leave unset for prod); " + missing_auth_message()
)


class _DeploymentSettings(DeploymentConfig, PipefyBaseSettings):
    """Test-only env reader for the deployment values (mirrors the app edge)."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")


class _SdkSettings(SdkConfig, PipefyBaseSettings):
    """Test-only env reader for the SDK knobs; ``deployment`` is injected."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")


class _AuthSettings(AuthConfig, PipefyBaseSettings):
    """Test-only env reader for the login subsystem; deployment + sa are injected."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_AUTH_")

    static_token: str | None = Field(
        default=None, validation_alias=AliasChoices("PIPEFY_TOKEN")
    )


class _ServiceAccountSettings(PipefyBaseSettings):
    """Test-only env reader for the service-account credential pair."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_SERVICE_ACCOUNT_")

    client_id: str | None = None
    client_secret: str | None = None

    def to_credentials(self) -> ServiceAccountCredentials | None:
        if self.client_id is None and self.client_secret is None:
            return None
        return ServiceAccountCredentials(
            client_id=self.client_id,  # type: ignore[arg-type]
            client_secret=self.client_secret,  # type: ignore[arg-type]
        )


def live_pipefy_config() -> SdkConfig:
    """Load ``SdkConfig`` from the process environment and optional ``.env`` file."""
    return _SdkSettings(deployment=_DeploymentSettings())


def live_endpoints() -> PipefyEndpoints:
    """Resolve the live ``PipefyEndpoints`` from the environment (integration tests)."""
    return load_sdk(load_deployment())[0]


def live_auth_config() -> AuthConfig:
    """Load ``AuthConfig`` from the process environment and optional ``.env`` file."""
    return _AuthSettings(
        deployment=_DeploymentSettings(),
        service_account_credentials=_ServiceAccountSettings().to_credentials(),
    )


def _try_resolve_live_auth() -> Auth | None:
    a = live_auth_config()
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
    # ``SdkConfig.base_url`` carries a prod default; consulting the
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
