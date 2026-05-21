"""Unit tests for PortalService multi-endpoint routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx_auth import OAuth2ClientCredentials

from pipefy_sdk.services.internal_api_client import InternalApiClient
from pipefy_sdk.services.portal_service import PortalService
from pipefy_sdk.settings import PipefySettings

INTERFACES_URL = "https://app.pipefy.com/graphql/interfaces"
MAIN_GRAPHQL_URL = "https://app.pipefy.com/graphql"
INTERNAL_API_URL = "https://app.pipefy.com/internal_api"
OAUTH_URL = "https://auth.pipefy.com/oauth/token"


@pytest.fixture
def mock_settings() -> PipefySettings:
    return PipefySettings(
        graphql_url=MAIN_GRAPHQL_URL,
        interfaces_graphql_url=INTERFACES_URL,
        internal_api_url=INTERNAL_API_URL,
        oauth_url=OAUTH_URL,
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


@pytest.fixture
def mock_auth() -> OAuth2ClientCredentials:
    return OAuth2ClientCredentials(
        token_url=OAUTH_URL,
        client_id="client_id",
        client_secret="client_secret",
    )


def _mock_internal_api_client() -> MagicMock:
    mock = MagicMock(spec=InternalApiClient)
    mock.execute_query = AsyncMock(return_value={"updateSubPortalElement": {}})
    return mock


@pytest.mark.unit
def test_portal_service_interfaces_client_uses_interfaces_graphql_url(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """PortalService wires BasePipefyClient to the Interfaces schema URL."""
    service = PortalService(
        settings=mock_settings,
        auth=mock_auth,
        internal_api_client=_mock_internal_api_client(),
    )
    assert service._interfaces_client.settings.graphql_url == INTERFACES_URL
    assert service._interfaces_client.settings.graphql_url != MAIN_GRAPHQL_URL


@pytest.mark.unit
@pytest.mark.asyncio
async def test_interfaces_query_routes_through_interfaces_client(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Representative Interfaces call delegates to the interfaces BasePipefyClient."""
    service = PortalService(
        settings=mock_settings,
        auth=mock_auth,
        internal_api_client=_mock_internal_api_client(),
    )
    service._interfaces_client.execute_query = AsyncMock(
        return_value={"interfaces": {"edges": []}}
    )

    query = "query { interfaces(orgUuid: $orgUuid) { edges { node { uuid } } } }"
    variables = {"orgUuid": "org-123"}
    result = await service.execute_interfaces_query(query, variables)

    service._interfaces_client.execute_query.assert_called_once()
    call_query, call_vars = service._interfaces_client.execute_query.call_args[0]
    assert call_query == query
    assert call_vars == variables
    assert result == {"interfaces": {"edges": []}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sub_portal_element_call_routes_through_internal_api_client(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Sub-portal wiring mutations delegate to InternalApiClient."""
    mock_internal = _mock_internal_api_client()
    service = PortalService(
        settings=mock_settings,
        auth=mock_auth,
        internal_api_client=mock_internal,
    )

    query = (
        "mutation updateSubPortalElement($input: UpdateSubPortalElementInput!) "
        "{ updateSubPortalElement(input: $input) { success } }"
    )
    variables = {
        "input": {
            "portalUuid": "portal-uuid",
            "elementId": 42,
            "subPortalUuid": "sub-uuid",
        }
    }
    result = await service.execute_internal_api_query(query, variables)

    mock_internal.execute_query.assert_called_once()
    call_query, call_vars = mock_internal.execute_query.call_args[0]
    assert call_query == query
    assert call_vars == variables
    assert result == {"updateSubPortalElement": {}}
