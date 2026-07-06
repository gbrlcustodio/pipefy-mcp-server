"""Pytest defaults for ``packages/mcp/tests``."""

import pytest

from pipefy_mcp.tools.validation_envelope import install_pipefy_validation_envelope

# Same validation envelope as ``server.py`` lifespan (idempotent).
install_pipefy_validation_envelope()

_AUTH_ENV_KEYS = (
    "PIPEFY_TOKEN",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET",
    "PIPEFY_OAUTH_CLIENT",
    "PIPEFY_OAUTH_SECRET",
    "PIPEFY_AUTH_URL",
    "PIPEFY_BASE_URL",
    "PIPEFY_DISABLE_STORED_SESSION",
    "PIPEFY_KEYCHAIN_BACKEND",
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def clear_auth_env(monkeypatch):
    """Strip ambient ``PIPEFY_*`` auth env so ``AuthSettings()`` is hermetic."""
    for key in _AUTH_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
