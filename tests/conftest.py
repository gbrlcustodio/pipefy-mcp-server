"""Fixtures for tests under ``tests/`` (SDK-adjacent suites at repo root)."""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
