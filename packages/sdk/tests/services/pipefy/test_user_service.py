"""Unit tests for UserService."""

from unittest.mock import AsyncMock

import pytest
from pipefy_auth import StaticBearerAuth

from pipefy_sdk.queries.me_queries import GET_ME_QUERY
from pipefy_sdk.services.user_service import UserService
from pipefy_sdk.settings import PipefySettings

_TEST_AUTH = StaticBearerAuth("test-bearer-token")


@pytest.fixture
def mock_settings():
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value):
    service = UserService(settings=mock_settings, auth=_TEST_AUTH)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_me_returns_identity(mock_settings):
    """`me` payload is unwrapped into the `MePayload` shape."""
    me_data = {"email": "user@pipefy.com", "name": "Pipefy User"}
    service = _make_service(mock_settings, {"me": me_data})

    result = await service.get_me()

    service.execute_query.assert_called_once()
    query_used, variables = service.execute_query.call_args[0]
    assert query_used is GET_ME_QUERY
    assert variables == {}
    assert result == me_data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_me_null_returns_none(mock_settings):
    """`me` is nullable in the Pipefy schema (verified via introspection)."""
    service = _make_service(mock_settings, {"me": None})

    assert await service.get_me() is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_me_null_name_is_passed_through(mock_settings):
    """`User.name` is nullable; the SDK preserves it rather than coercing."""
    service = _make_service(
        mock_settings, {"me": {"email": "user@pipefy.com", "name": None}}
    )

    result = await service.get_me()

    assert result == {"email": "user@pipefy.com", "name": None}
