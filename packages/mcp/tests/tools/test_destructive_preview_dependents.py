"""Guard-level tests for optional ``dependents_resolver`` (REQ-1)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation

RESOURCE = "phase field (ID: 99)"
TOOL_NAME = "delete_phase_field"
IDENTITY = {"field_id": "99"}


def _minimal_ctx():
    ctx = MagicMock()
    ctx.session = MagicMock()
    ctx.elicit = AsyncMock()
    return ctx


async def _check(ctx, *, confirm, dependents_resolver=None, confirmation_token=None):
    return await check_destructive_confirmation(
        ctx,
        confirm=confirm,
        resource_descriptor=RESOURCE,
        resource_identity=IDENTITY,
        tool_name=TOOL_NAME,
        confirmation_token=confirmation_token,
        dependents_resolver=dependents_resolver,
    )


@pytest.mark.anyio
async def test_no_resolver_shape_unchanged():
    ctx = _minimal_ctx()
    payload = await _check(ctx, confirm=False)
    assert payload is not None
    assert set(payload.keys()) == {
        "success",
        "requires_confirmation",
        "resource",
        "message",
        "confirmation_token",
    }
    token = payload["confirmation_token"]
    assert isinstance(token, str)
    assert token
    assert token.startswith("v1.")
    assert "dependents" not in payload


@pytest.mark.anyio
async def test_resolver_returns_none_no_enrichment():
    ctx = _minimal_ctx()

    async def resolver():
        return None

    payload = await _check(ctx, confirm=False, dependents_resolver=resolver)
    assert payload is not None
    assert "dependents" not in payload


@pytest.mark.anyio
async def test_resolver_returns_empty_dict_no_enrichment():
    ctx = _minimal_ctx()

    async def resolver():
        return {}

    payload = await _check(ctx, confirm=False, dependents_resolver=resolver)
    assert payload is not None
    assert "dependents" not in payload


@pytest.mark.anyio
async def test_resolver_returns_dict_enriches_preview():
    ctx = _minimal_ctx()
    deps = {"field_conditions": [{"id": "c1"}], "hint": "clean up"}

    async def resolver():
        return deps

    payload = await _check(ctx, confirm=False, dependents_resolver=resolver)
    assert payload is not None
    assert payload["dependents"] == deps
    assert payload["resource"] == RESOURCE
    assert payload["success"] is False


@pytest.mark.anyio
async def test_resolver_raises_degrades_silently():
    ctx = _minimal_ctx()

    async def resolver():
        raise RuntimeError("boom")

    payload = await _check(ctx, confirm=False, dependents_resolver=resolver)
    assert payload is not None
    assert "dependents" not in payload
    assert payload["resource"] == RESOURCE


@pytest.mark.anyio
async def test_confirm_true_never_invokes_resolver():
    ctx = _minimal_ctx()
    calls = 0

    async def resolver():
        nonlocal calls
        calls += 1
        return {"should_not": "appear"}

    preview = await _check(ctx, confirm=False, dependents_resolver=resolver)
    assert preview is not None
    token = preview["confirmation_token"]
    calls = 0

    result = await _check(
        ctx,
        confirm=True,
        confirmation_token=token,
        dependents_resolver=resolver,
    )
    assert result is None
    assert calls == 0
