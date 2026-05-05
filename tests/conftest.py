"""Root test configuration (shared fixtures for all test directories)."""

import pytest

from pipefy_mcp.tools.validation_envelope import install_pipefy_validation_envelope

# Mirror the production wiring in ``server.py``'s lifespan so every in-memory
# FastMCP instance constructed in tests also goes through ``PipefyValidationTool``.
# The patch is idempotent — calling it here is safe regardless of other imports.
install_pipefy_validation_envelope()


@pytest.fixture
def anyio_backend():
    return "asyncio"
