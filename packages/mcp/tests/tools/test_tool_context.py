"""Tests for resolving the request-scoped client from the lifespan context."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipefy_mcp.core.runtime import McpRuntime, StartupIdentity
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.tool_context import get_pipefy_client


def _runtime() -> McpRuntime:
    """A pure runtime (no client built) to hold a preset ``pipefy_client``."""
    return McpRuntime(settings, StartupIdentity())


def _ctx_with_runtime(runtime: McpRuntime) -> Mock:
    """A minimal Context whose request_context carries ``runtime``."""
    ctx = Mock()
    ctx.request_context = SimpleNamespace(lifespan_context=runtime)
    return ctx


@pytest.mark.unit
def test_returns_the_client_held_by_the_lifespan_runtime():
    runtime = _runtime()
    client = Mock()
    runtime.pipefy_client = client

    assert get_pipefy_client(_ctx_with_runtime(runtime)) is client


@pytest.mark.unit
def test_reads_the_live_client_off_the_runtime():
    """The client is read per call, not bound at registration."""
    runtime = _runtime()
    first, second = Mock(), Mock()
    ctx = _ctx_with_runtime(runtime)

    runtime.pipefy_client = first
    assert get_pipefy_client(ctx) is first

    runtime.pipefy_client = second
    assert get_pipefy_client(ctx) is second


@pytest.mark.unit
def test_raises_when_no_client_initialized_yet():
    runtime = _runtime()
    runtime.pipefy_client = None

    with pytest.raises(RuntimeError, match="client is not initialized"):
        get_pipefy_client(_ctx_with_runtime(runtime))
