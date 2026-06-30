"""Live Pipefy credentials helpers for SDK integration tests (no MCP imports).

The libraries are env-free; these helpers drive the real env edge
(``pipefy_infra.env`` / ``pipefy_sdk.env`` / ``pipefy_auth.env``) to resolve the
refined value objects an integration test needs from the operator's shell env.
"""

from __future__ import annotations

import os

import pytest
from httpx import Auth
from pipefy_auth import CredentialSources, missing_auth_message, resolve_pipefy_auth
from pipefy_auth.env import load_auth
from pipefy_infra.deployment import DeploymentConfig
from pipefy_infra.env import load_deployment

from pipefy_sdk.endpoints import PipefyEndpoints
from pipefy_sdk.env import load_sdk

_MISSING_CREDS_MESSAGE = (
    "Pipefy credentials not configured: set PIPEFY_BASE_URL to your "
    "Pipefy API host (or leave unset for prod); " + missing_auth_message()
)


def live_deployment() -> DeploymentConfig:
    """Resolve the live ``DeploymentConfig`` from env / ``.env`` / ``config.toml``."""
    return load_deployment()


def live_endpoints() -> PipefyEndpoints:
    """Resolve the live ``PipefyEndpoints`` from the environment (integration tests)."""
    return load_sdk(load_deployment())[0]


def live_credentials() -> CredentialSources:
    """Resolve the live ``CredentialSources`` bundle from the environment."""
    return load_auth(load_deployment())[0]


def _try_resolve_live_auth() -> Auth | None:
    sources = live_credentials()
    # ``oidc_client=None``: a stray ``pipefy auth login`` on a dev machine would
    # otherwise satisfy live-creds detection via the developer's personal session.
    return resolve_pipefy_auth(
        CredentialSources(
            static_token=sources.static_token,
            service_account=sources.service_account,
            oidc_client=None,
        )
    )


def live_resolved_auth() -> Auth:
    """Resolve a live ``httpx.Auth`` via the production precedence chain, or skip the test."""
    resolved = _try_resolve_live_auth()
    if resolved is None:
        pytest.skip(_MISSING_CREDS_MESSAGE)
    return resolved


def pipefy_live_configured() -> bool:
    """Return True when a Pipefy host and a resolvable auth tier are both configured."""
    # The deployment carries a prod default, so gate on the explicit env var
    # instead of the resolved host; otherwise live tests would switch on for
    # every dev machine that has any auth tier configured.
    has_url = bool(os.environ.get("PIPEFY_BASE_URL", "").strip())
    return has_url and _try_resolve_live_auth() is not None


def require_live_creds() -> None:
    """Skip the current test if live credentials are not configured."""
    if not pipefy_live_configured():
        pytest.skip(_MISSING_CREDS_MESSAGE)
