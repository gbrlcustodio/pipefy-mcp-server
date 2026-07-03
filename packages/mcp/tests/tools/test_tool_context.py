"""Tests for resolving the request-scoped client from the lifespan context."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipefy_mcp.core.runtime import McpRuntime, RequestScopedIdentity
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.tool_context import get_pipefy_client


def _runtime() -> McpRuntime:
    """A runtime built with no credential resolution, to hold a stubbed session.

    The request-scoped source builds the engine without keychain or network I/O,
    so the runtime constructs cleanly; tests override ``session_for_request``.
    """
    return McpRuntime(settings, RequestScopedIdentity())


def _ctx_with_runtime(runtime: McpRuntime, request: object | None = None) -> Mock:
    """A minimal Context whose request_context carries ``runtime`` and ``request``."""
    ctx = Mock()
    ctx.request_context = SimpleNamespace(lifespan_context=runtime, request=request)
    return ctx


@pytest.mark.unit
def test_returns_the_session_opened_for_the_requests_identity():
    runtime = _runtime()
    client = Mock()
    request = object()
    seen: list[object | None] = []
    runtime.session_for_request = lambda req: seen.append(req) or client

    ctx = _ctx_with_runtime(runtime, request)
    assert get_pipefy_client(ctx) is client
    # The message's own request is threaded through, so identity is per-caller.
    assert seen == [request]


@pytest.mark.unit
def test_opens_a_session_per_call():
    """A session is opened per call, not bound at registration."""
    runtime = _runtime()
    first, second = Mock(), Mock()
    ctx = _ctx_with_runtime(runtime)

    runtime.session_for_request = lambda req: first
    assert get_pipefy_client(ctx) is first

    runtime.session_for_request = lambda req: second
    assert get_pipefy_client(ctx) is second
