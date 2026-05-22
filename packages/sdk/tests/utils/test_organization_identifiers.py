"""Tests for organization UUID vs numeric id resolution helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pipefy_sdk.queries.observability_queries import RESOLVE_ORGANIZATION_UUID_QUERY
from pipefy_sdk.utils.organization_identifiers import (
    looks_like_uuid,
    resolve_organization_uuid,
)

_ORG_UUID = "550e8400-e29b-41d4-a716-446655440000"
_NUMERIC_ORG_ID = "302398434"


def test_looks_like_uuid_accepts_valid_uuid() -> None:
    assert looks_like_uuid(_ORG_UUID) is True


def test_looks_like_uuid_rejects_numeric_id() -> None:
    assert looks_like_uuid(_NUMERIC_ORG_ID) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_organization_uuid_passes_through_uuid() -> None:
    execute_query = AsyncMock()

    result = await resolve_organization_uuid(execute_query, _ORG_UUID)

    assert result == _ORG_UUID
    execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_organization_uuid_coerces_int_before_resolve() -> None:
    execute_query = AsyncMock(
        return_value={"organization": {"uuid": _ORG_UUID}},
    )

    result = await resolve_organization_uuid(execute_query, 302398434)

    assert result == _ORG_UUID
    execute_query.assert_awaited_once_with(
        RESOLVE_ORGANIZATION_UUID_QUERY,
        {"id": _NUMERIC_ORG_ID},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_organization_uuid_resolves_numeric_string() -> None:
    execute_query = AsyncMock(
        return_value={"organization": {"uuid": _ORG_UUID}},
    )

    result = await resolve_organization_uuid(execute_query, _NUMERIC_ORG_ID)

    assert result == _ORG_UUID
    execute_query.assert_awaited_once_with(
        RESOLVE_ORGANIZATION_UUID_QUERY,
        {"id": _NUMERIC_ORG_ID},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_organization_uuid_rejects_empty() -> None:
    execute_query = AsyncMock()

    with pytest.raises(ValueError, match="must be non-empty"):
        await resolve_organization_uuid(execute_query, "   ")

    execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_organization_uuid_rejects_invalid_identifier() -> None:
    execute_query = AsyncMock()

    with pytest.raises(ValueError, match="must be a UUID or numeric id"):
        await resolve_organization_uuid(execute_query, "not-a-uuid-or-digits")

    execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_organization_uuid_org_not_found() -> None:
    execute_query = AsyncMock(return_value={"organization": None})

    with pytest.raises(ValueError, match="Organization not found"):
        await resolve_organization_uuid(execute_query, _NUMERIC_ORG_ID)
