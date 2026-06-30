"""Pytest defaults for ``packages/mcp/tests``."""

import pytest

from pipefy_mcp.runtime import reset_runtime
from pipefy_mcp.tools.validation_envelope import install_pipefy_validation_envelope

# Same validation envelope as ``server.py`` lifespan (idempotent).
install_pipefy_validation_envelope()


@pytest.fixture(autouse=True)
def _reset_mcp_settings_cache():
    """Clear the lazy get_runtime() cache around each test.

    The cache reintroduces the cross-test env leak the per-construction model
    avoided: without this, the first test to call get_runtime() would pin the
    settings for the whole session.
    """
    reset_runtime()
    yield
    reset_runtime()


@pytest.fixture
def anyio_backend():
    return "asyncio"
