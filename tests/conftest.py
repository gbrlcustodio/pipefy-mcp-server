"""Fixtures for repo-root ``tests/`` (not ``packages/mcp/tests``)."""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
