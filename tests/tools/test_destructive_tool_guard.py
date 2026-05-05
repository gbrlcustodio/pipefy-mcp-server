"""Tests for the reusable destructive tool confirmation guard."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation

RESOURCE = "phase 'Initial' (ID: 42)"


def _make_ctx(*, can_elicit):
    ctx = MagicMock()
    ctx.session.client_params.capabilities.elicitation = can_elicit
    ctx.elicit = AsyncMock()
    return ctx


@pytest.mark.anyio
class TestNoElicitation:
    async def test_no_confirm_returns_preview(self):
        ctx = _make_ctx(can_elicit=False)
        payload = await check_destructive_confirmation(
            ctx, confirm=False, resource_descriptor=RESOURCE
        )
        assert payload is not None
        assert payload["success"] is False
        assert payload["requires_confirmation"] is True
        assert payload["resource"] == RESOURCE
        assert "confirm=True" in payload["message"]
        ctx.elicit.assert_not_called()

    async def test_confirm_true_returns_none(self):
        ctx = _make_ctx(can_elicit=False)
        result = await check_destructive_confirmation(
            ctx, confirm=True, resource_descriptor=RESOURCE
        )
        assert result is None
        ctx.elicit.assert_not_called()


@pytest.mark.anyio
class TestClientAdvertisesElicitation:
    """Even when the client supports elicitation, only ``confirm=True`` authorizes deletion."""

    async def test_confirm_false_returns_preview_and_never_elicits(self):
        ctx = _make_ctx(can_elicit=True)
        payload = await check_destructive_confirmation(
            ctx, confirm=False, resource_descriptor=RESOURCE
        )
        assert payload is not None
        assert payload["success"] is False
        assert payload["requires_confirmation"] is True
        assert payload["resource"] == RESOURCE
        assert "confirm=True" in payload["message"]
        ctx.elicit.assert_not_called()

    async def test_confirm_true_returns_none_without_elicit(self):
        ctx = _make_ctx(can_elicit=True)
        result = await check_destructive_confirmation(
            ctx, confirm=True, resource_descriptor=RESOURCE
        )
        assert result is None
        ctx.elicit.assert_not_called()


@pytest.mark.anyio
class TestMissingCapabilityMetadata:
    async def test_no_client_params_returns_preview(self):
        ctx = MagicMock()
        ctx.session = SimpleNamespace()
        ctx.elicit = AsyncMock()
        payload = await check_destructive_confirmation(
            ctx, confirm=False, resource_descriptor=RESOURCE
        )
        assert payload is not None
        assert payload["success"] is False
        assert payload["requires_confirmation"] is True
        assert payload["resource"] == RESOURCE
        assert "confirm=True" in payload["message"]
        ctx.elicit.assert_not_called()

    async def test_client_params_without_capabilities_returns_preview(self):
        ctx = MagicMock()
        ctx.session = SimpleNamespace(client_params=SimpleNamespace())
        ctx.elicit = AsyncMock()
        payload = await check_destructive_confirmation(
            ctx, confirm=False, resource_descriptor=RESOURCE
        )
        assert payload is not None
        assert payload["success"] is False
        assert payload["requires_confirmation"] is True
        assert payload["resource"] == RESOURCE
        assert "confirm=True" in payload["message"]
        ctx.elicit.assert_not_called()

    async def test_capabilities_without_elicitation_attr_returns_preview(self):
        ctx = MagicMock()
        ctx.session = SimpleNamespace(
            client_params=SimpleNamespace(capabilities=SimpleNamespace()),
        )
        ctx.elicit = AsyncMock()
        payload = await check_destructive_confirmation(
            ctx, confirm=False, resource_descriptor=RESOURCE
        )
        assert payload is not None
        assert payload["success"] is False
        assert payload["requires_confirmation"] is True
        assert payload["resource"] == RESOURCE
        ctx.elicit.assert_not_called()
