"""Unit tests for PortalService multi-endpoint routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx_auth import OAuth2ClientCredentials

from pipefy_sdk.queries.observability_queries import RESOLVE_ORGANIZATION_UUID_QUERY
from pipefy_sdk.queries.portal_queries import GET_PORTAL_QUERY, LIST_PORTALS_QUERY
from pipefy_sdk.services.internal_api_client import InternalApiClient
from pipefy_sdk.services.portal_service import PortalService
from pipefy_sdk.settings import PipefySettings

INTERFACES_URL = "https://app.pipefy.com/graphql/interfaces"
MAIN_GRAPHQL_URL = "https://app.pipefy.com/graphql"
INTERNAL_API_URL = "https://app.pipefy.com/internal_api"
OAUTH_URL = "https://auth.pipefy.com/oauth/token"
_ORG_UUID_FOR_TESTS = "341c1327-261c-4766-bb96-7953e4c3970d"
_OTHER_ORG_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
_NUMERIC_ORG_ID = "302398434"


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
    assert service._graphql_client.settings.graphql_url == MAIN_GRAPHQL_URL


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


def _make_interfaces_service(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
    return_value: dict,
) -> PortalService:
    service = PortalService(
        settings=mock_settings,
        auth=mock_auth,
        internal_api_client=_mock_internal_api_client(),
    )
    service._interfaces_client.execute_query = AsyncMock(return_value=return_value)
    return service


_PORTAL_LIST_GRAPHQL_NODE = {
    "id": "portal-uuid-1",
    "name": "Main Portal",
    "visibility": "internal",
    "subType": "portal",
}

_PORTAL_LIST_NODE = {
    **_PORTAL_LIST_GRAPHQL_NODE,
    "uuid": "portal-uuid-1",
}

_PORTAL_DETAIL_GRAPHQL = {
    "id": "portal-uuid-1",
    "name": "Main Portal",
    "visibility": "public",
    "published": True,
    "pages": [
        {
            "id": "page-1",
            "title": "Home",
            "elements": [
                {
                    "id": "el-1",
                    "type": "forms",
                    "metadata": {"formId": "123"},
                }
            ],
        }
    ],
    "subPortals": [{"id": "sub-1", "name": "Sub Portal 1", "published": False}],
}

_PORTAL_DETAIL = {
    **_PORTAL_DETAIL_GRAPHQL,
    "uuid": "portal-uuid-1",
    "pages": [
        {
            "id": "page-1",
            "uuid": "page-1",
            "title": "Home",
            "elements": [
                {
                    "id": "el-1",
                    "uuid": "el-1",
                    "type": "forms",
                    "metadata": {"formId": "123"},
                }
            ],
        }
    ],
    "subPortals": [
        {"id": "sub-1", "uuid": "sub-1", "name": "Sub Portal 1", "published": False}
    ],
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_portals_returns_portal_nodes(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """list_portals unwraps Relay edges into a flat list of portal dicts."""
    response = {
        "interfaces": {
            "edges": [{"node": _PORTAL_LIST_GRAPHQL_NODE}],
        }
    }
    service = _make_interfaces_service(mock_settings, mock_auth, response)

    result = await service.list_portals(_ORG_UUID_FOR_TESTS)

    assert result == [_PORTAL_LIST_NODE]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_portals_passes_org_uuid_and_portal_filter(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """list_portals queries interfaces with org_uuid and filterBySubType portal."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"interfaces": {"edges": []}},
    )

    await service.list_portals(_OTHER_ORG_UUID)

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    assert query_used is LIST_PORTALS_QUERY
    assert variables == {"org_uuid": _OTHER_ORG_UUID, "filterBySubType": "portal"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_portals_passes_search_term_when_provided(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Optional search_term is forwarded as searchTerm to the GraphQL query."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"interfaces": {"edges": []}},
    )

    await service.list_portals(_ORG_UUID_FOR_TESTS, search_term="intake")

    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    assert query_used is LIST_PORTALS_QUERY
    assert variables == {
        "org_uuid": _ORG_UUID_FOR_TESTS,
        "filterBySubType": "portal",
        "searchTerm": "intake",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_portals_empty_returns_empty_list(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """When no portals exist, list_portals returns an empty list."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"interfaces": {"edges": []}},
    )

    result = await service.list_portals(_ORG_UUID_FOR_TESTS)

    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_portals_uuid_org_identifier_passes_through_unchanged(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """UUID-shaped org identifiers skip resolve and go straight to Interfaces."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"interfaces": {"edges": []}},
    )
    service._graphql_client.execute_query = AsyncMock()

    await service.list_portals(_ORG_UUID_FOR_TESTS)

    service._graphql_client.execute_query.assert_not_called()
    _, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables["org_uuid"] == _ORG_UUID_FOR_TESTS


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_portals_numeric_org_id_resolves_via_main_graphql_client(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Numeric org ids resolve on the public GraphQL client before Interfaces list."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"interfaces": {"edges": []}},
    )
    service._graphql_client.execute_query = AsyncMock(
        return_value={"organization": {"uuid": _ORG_UUID_FOR_TESTS}}
    )

    await service.list_portals(_NUMERIC_ORG_ID)

    service._graphql_client.execute_query.assert_called_once_with(
        RESOLVE_ORGANIZATION_UUID_QUERY,
        {"id": _NUMERIC_ORG_ID},
    )
    _, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables["org_uuid"] == _ORG_UUID_FOR_TESTS


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_portals_rejects_empty_org_identifier(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Empty org identifiers raise ValueError before any GraphQL call."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"interfaces": {"edges": []}},
    )

    with pytest.raises(ValueError, match="must be non-empty"):
        await service.list_portals("   ")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_portals_rejects_invalid_org_identifier(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Non-UUID, non-numeric org identifiers raise ValueError."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"interfaces": {"edges": []}},
    )

    with pytest.raises(ValueError, match="must be a UUID or numeric id"):
        await service.list_portals("not-a-uuid-or-digits")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_portals_org_not_found_on_resolve_raises_value_error(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """When resolve yields no uuid, list_portals raises ValueError."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"interfaces": {"edges": []}},
    )
    service._graphql_client.execute_query = AsyncMock(
        return_value={"organization": None}
    )

    with pytest.raises(ValueError, match="Organization not found"):
        await service.list_portals(_NUMERIC_ORG_ID)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_portal_returns_full_portal_shape(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """get_portal returns portal metadata, pages, elements, and sub-portals."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"portalInterface": _PORTAL_DETAIL_GRAPHQL},
    )

    result = await service.get_portal("portal-uuid-1")

    assert result == _PORTAL_DETAIL
    assert result["published"] is True
    assert len(result["pages"]) == 1
    assert result["subPortals"][0]["uuid"] == "sub-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_portal_not_found_raises_value_error(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """When portalInterface is null, get_portal raises ValueError with the UUID."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"portalInterface": None},
    )

    with pytest.raises(ValueError, match="portal-uuid-missing"):
        await service.get_portal("portal-uuid-missing")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_portal_uses_correct_variables(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """get_portal passes the portal UUID as the uuid GraphQL variable."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"portalInterface": _PORTAL_DETAIL},
    )

    await service.get_portal("uuid-abc")

    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    assert query_used is GET_PORTAL_QUERY
    assert variables == {"uuid": "uuid-abc"}
