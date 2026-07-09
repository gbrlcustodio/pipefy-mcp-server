"""Pytest defaults for ``packages/mcp/tests``."""

import pytest

from pipefy_mcp.observability.json_logging import reset_observability_logging
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


@pytest.fixture(autouse=True)
def _reset_observability_logging_between_tests():
    """Drop observability handlers after every test.

    The observability logger is process-global. Any test that reaches
    ``configure_observability_logging`` (directly or through ``run_server``)
    would otherwise leave a handler bound to that test's captured stderr, and a
    later ``emit_structured_event`` in an unrelated test would write into a
    closed stream.
    """
    yield
    reset_observability_logging()
