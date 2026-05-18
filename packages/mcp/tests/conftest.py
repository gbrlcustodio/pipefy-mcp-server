"""Pytest defaults for ``packages/mcp/tests``."""

import pytest

from pipefy_mcp.tools.validation_envelope import install_pipefy_validation_envelope

# Same validation envelope as ``server.py`` lifespan (idempotent).
install_pipefy_validation_envelope()


@pytest.fixture
def anyio_backend():
    return "asyncio"
