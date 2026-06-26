"""Unit tests for UserService."""

import pytest
from _shared.mock_clients import mock_executor

from pipefy_sdk.queries.me_queries import GET_ME_QUERY
from pipefy_sdk.services.user_service import UserService


def _make_service(return_value):
    executor = mock_executor(return_value)
    return UserService(executor=executor), executor


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_me_returns_identity():
    """`me` payload is unwrapped into the `MePayload` shape."""
    me_data = {"id": "301", "email": "user@pipefy.com", "name": "Pipefy User"}
    service, executor = _make_service({"me": me_data})

    result = await service.get_me()

    executor.execute_query.assert_called_once()
    query_used, variables = executor.execute_query.call_args[0]
    assert query_used is GET_ME_QUERY
    assert variables == {}
    assert result == me_data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_me_null_returns_none():
    """`me` is nullable in the Pipefy schema (verified via introspection)."""
    service, _ = _make_service({"me": None})

    assert await service.get_me() is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_me_null_name_is_passed_through():
    """`User.name` is nullable; the SDK preserves it rather than coercing."""
    service, _ = _make_service(
        {"me": {"id": "301", "email": "user@pipefy.com", "name": None}}
    )

    result = await service.get_me()

    assert result == {"id": "301", "email": "user@pipefy.com", "name": None}
