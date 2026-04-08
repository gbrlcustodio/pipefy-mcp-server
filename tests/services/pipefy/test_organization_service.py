"""Unit tests for OrganizationService."""

from unittest.mock import AsyncMock

import pytest

from pipefy_mcp.services.pipefy.organization_service import OrganizationService
from pipefy_mcp.services.pipefy.queries.organization_queries import (
    GET_ORGANIZATION_QUERY,
)
from pipefy_mcp.settings import PipefySettings


@pytest.fixture
def mock_settings():
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value):
    service = OrganizationService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_organization_returns_org_details(mock_settings):
    """Fetching a valid org returns its details."""
    org_data = {
        "id": "123",
        "uuid": "abc-def-ghi",
        "name": "My Org",
        "planName": "Business",
        "membersCount": 42,
        "pipesCount": 10,
        "createdAt": "2023-01-01T00:00:00Z",
        "role": "admin",
    }
    service = _make_service(mock_settings, {"organization": org_data})
    result = await service.get_organization("123")

    service.execute_query.assert_called_once()
    query_used, variables = service.execute_query.call_args[0]
    assert query_used is GET_ORGANIZATION_QUERY
    assert variables == {"id": "123"}
    assert result == org_data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_organization_not_found_raises_value_error(mock_settings):
    """When organization is null, raise ValueError."""
    service = _make_service(mock_settings, {"organization": None})

    with pytest.raises(ValueError, match="999"):
        await service.get_organization("999")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_organization_uses_correct_query_and_variables(mock_settings):
    """Verify the correct query constant and variable shape."""
    org_data = {"id": "456", "uuid": "xyz", "name": "Other Org"}
    service = _make_service(mock_settings, {"organization": org_data})
    await service.get_organization("456")

    query_used, variables = service.execute_query.call_args[0]
    assert query_used is GET_ORGANIZATION_QUERY
    assert variables == {"id": "456"}
