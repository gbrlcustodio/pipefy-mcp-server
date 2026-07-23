"""Unit tests for OrganizationService."""

import pytest
from _shared.mock_clients import mock_executor

from pipefy_sdk.queries.organization_queries import (
    GET_ORGANIZATION_QUERY,
    LIST_ORGANIZATIONS_QUERY,
)
from pipefy_sdk.services.organization_service import OrganizationService


def _make_service(return_value):
    executor = mock_executor(return_value)
    return OrganizationService(executor=executor), executor


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_organization_returns_org_details():
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
    service, executor = _make_service({"organization": org_data})
    result = await service.get_organization("123")

    executor.execute_query.assert_called_once()
    query_used, variables = executor.execute_query.call_args[0]
    assert query_used is GET_ORGANIZATION_QUERY
    assert variables == {"id": "123"}
    assert result == org_data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_organization_not_found_raises_value_error():
    """When organization is null, raise ValueError."""
    service, _ = _make_service({"organization": None})

    with pytest.raises(ValueError, match="999"):
        await service.get_organization("999")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_organization_uses_correct_query_and_variables():
    """Verify the correct query constant and variable shape."""
    org_data = {"id": "456", "uuid": "xyz", "name": "Other Org"}
    service, executor = _make_service({"organization": org_data})
    await service.get_organization("456")

    query_used, variables = executor.execute_query.call_args[0]
    assert query_used is GET_ORGANIZATION_QUERY
    assert variables == {"id": "456"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_organizations_returns_accessible_orgs():
    """Listing returns every accessible org, querying with no variables."""
    orgs = [
        {"id": "123", "uuid": "abc", "name": "My Org", "role": "admin"},
        {"id": "456", "uuid": "def", "name": "Other Org", "role": "member"},
    ]
    service, executor = _make_service({"organizations": orgs})
    result = await service.list_organizations()

    query_used, variables = executor.execute_query.call_args[0]
    assert query_used is LIST_ORGANIZATIONS_QUERY
    assert variables == {}
    assert result == orgs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_organizations_empty_is_not_an_error():
    """No accessible orgs returns an empty list, not a raise (unlike get)."""
    service, _ = _make_service({"organizations": None})
    assert await service.list_organizations() == []
