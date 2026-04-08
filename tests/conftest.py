"""Root test configuration (shared fixtures for all test directories)."""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
