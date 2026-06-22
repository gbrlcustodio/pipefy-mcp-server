"""Tests for resolving the request-scoped client from the lifespan context."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.tools.tool_context import get_pipefy_client


def _ctx_with_container(container: ServicesContainer) -> Mock:
    """A minimal Context whose request_context carries ``container``."""
    ctx = Mock()
    ctx.request_context = SimpleNamespace(lifespan_context=container)
    return ctx


@pytest.mark.unit
def test_returns_the_client_held_by_the_lifespan_container():
    container = ServicesContainer()
    client = Mock()
    container.pipefy_client = client

    assert get_pipefy_client(_ctx_with_container(container)) is client


@pytest.mark.unit
def test_follows_a_client_swap_on_the_same_container():
    """A re-initialized container is picked up; nothing is bound at registration."""
    container = ServicesContainer()
    first, second = Mock(), Mock()
    ctx = _ctx_with_container(container)

    container.pipefy_client = first
    assert get_pipefy_client(ctx) is first

    container.pipefy_client = second
    assert get_pipefy_client(ctx) is second


@pytest.mark.unit
def test_raises_when_no_client_initialized_yet():
    container = ServicesContainer()
    container.pipefy_client = None

    with pytest.raises(RuntimeError, match="client is not initialized"):
        get_pipefy_client(_ctx_with_container(container))
