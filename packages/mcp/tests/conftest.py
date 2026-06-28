"""Pytest defaults for ``packages/mcp/tests``."""

import pytest

from pipefy_mcp.settings import reset_settings
from pipefy_mcp.tools.validation_envelope import install_pipefy_validation_envelope

# Same validation envelope as ``server.py`` lifespan (idempotent).
install_pipefy_validation_envelope()


@pytest.fixture(autouse=True)
def _reset_mcp_settings_cache():
    """Clear the lazy get_settings() cache around each test.

    The cache reintroduces the cross-test env leak the per-construction model
    avoided: without this, the first test to call get_settings() would pin the
    settings for the whole session.
    """
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def anyio_backend():
    return "asyncio"
