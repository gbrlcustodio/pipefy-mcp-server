"""Tests for the reusable destructive tool confirmation guard."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation

RESOURCE = "phase 'Initial' (ID: 42)"


def _make_ctx(*, can_elicit, elicit_result=None, elicit_side_effect=None):
    ctx = MagicMock()
    ctx.session.client_params.capabilities.elicitation = can_elicit
    if elicit_side_effect:
        ctx.elicit = AsyncMock(side_effect=elicit_side_effect)
    elif elicit_result is not None:
        ctx.elicit = AsyncMock(return_value=elicit_result)
    else:
        ctx.elicit = AsyncMock()
    return ctx


def _elicit_result(action, confirm_value=True):
    result = MagicMock()
    result.action = action
    result.data.model_dump.return_value = {"confirm": confirm_value}
    return result


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

    async def test_confirm_true_returns_none(self):
        ctx = _make_ctx(can_elicit=False)
        result = await check_destructive_confirmation(
            ctx, confirm=True, resource_descriptor=RESOURCE
        )
        assert result is None


@pytest.mark.anyio
class TestWithElicitation:
    async def test_user_accepts_returns_none(self):
        ctx = _make_ctx(
            can_elicit=True,
            elicit_result=_elicit_result(action="accept", confirm_value=True),
        )
        result = await check_destructive_confirmation(
            ctx, confirm=False, resource_descriptor=RESOURCE
        )
        assert result is None

    async def test_user_declines_returns_cancel(self):
        ctx = _make_ctx(
            can_elicit=True,
            elicit_result=_elicit_result(action="decline"),
        )
        payload = await check_destructive_confirmation(
            ctx, confirm=False, resource_descriptor=RESOURCE
        )
        assert payload is not None
        assert payload["success"] is False
        assert "cancelled" in payload["error"].lower()

    async def test_user_accepts_but_confirm_false_returns_cancel(self):
        ctx = _make_ctx(
            can_elicit=True,
            elicit_result=_elicit_result(action="accept", confirm_value=False),
        )
        payload = await check_destructive_confirmation(
            ctx, confirm=False, resource_descriptor=RESOURCE
        )
        assert payload is not None
        assert payload["success"] is False

    async def test_elicitation_raises_returns_error(self):
        ctx = _make_ctx(
            can_elicit=True,
            elicit_side_effect=RuntimeError("elicit broke"),
        )
        payload = await check_destructive_confirmation(
            ctx, confirm=False, resource_descriptor=RESOURCE
        )
        assert payload is not None
        assert payload["success"] is False
        assert "Failed to request confirmation" in payload["error"]

    async def test_confirm_true_ignored_when_elicitation_available(self):
        """Even with confirm=True, elicitation takes precedence when available."""
        ctx = _make_ctx(
            can_elicit=True,
            elicit_result=_elicit_result(action="accept", confirm_value=True),
        )
        result = await check_destructive_confirmation(
            ctx, confirm=True, resource_descriptor=RESOURCE
        )
        assert result is None
        ctx.elicit.assert_called_once()
