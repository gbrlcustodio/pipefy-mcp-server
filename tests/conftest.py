"""Shared pytest configuration for the repo-root ``tests/`` tree.

This directory holds unit and integration tests for packages that still live
under ``tests/`` (for example SDK-adjacent suites). There are no ``test_*.py``
files at the root of ``tests/`` itself—only subpackages such as ``tests/tools``
and ``tests/services``. MCP-focused collections live under ``packages/mcp/tests``.
"""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
