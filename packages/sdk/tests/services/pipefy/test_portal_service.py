"""Unit tests for PortalService multi-endpoint routing."""

from __future__ import annotations

import importlib
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from _shared.fixture_ids import (
    EXAMPLE_NUMERIC_ORG_ID,
    EXAMPLE_ORG_UUID,
    EXAMPLE_OTHER_ORG_UUID,
    EXAMPLE_PIPE_REPO_ID,
)
from _shared.mock_clients import mock_internal_api_client
from gql.transport.exceptions import TransportQueryError
from httpx_auth import OAuth2ClientCredentials
from pydantic import ValidationError

from pipefy_sdk.exceptions import PortalPermissionError
from pipefy_sdk.queries.observability_queries import RESOLVE_ORGANIZATION_UUID_QUERY
from pipefy_sdk.queries.portal_queries import GET_PORTAL_QUERY, LIST_PORTALS_QUERY
from pipefy_sdk.services.portal_service import PortalService
from pipefy_sdk.settings import PipefySettings

BASE_URL = "https://app.pipefy.com"
INTERFACES_URL = "https://app.pipefy.com/graphql/interfaces"
MAIN_GRAPHQL_URL = "https://app.pipefy.com/graphql"
OAUTH_URL = "https://app.pipefy.com/oauth/token"


@pytest.fixture
def mock_settings() -> PipefySettings:
    return PipefySettings(base_url=BASE_URL)


@pytest.fixture
def mock_auth() -> OAuth2ClientCredentials:
    return OAuth2ClientCredentials(
        token_url=OAUTH_URL,
        client_id="client_id",
        client_secret="client_secret",
    )


def _mock_internal_api_client() -> MagicMock:
    return mock_internal_api_client({"updateSubPortalElement": {}})


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
    assert service._interfaces_client._graphql_url == INTERFACES_URL
    assert service._interfaces_client._graphql_url != MAIN_GRAPHQL_URL
    assert service._graphql_client._graphql_url == MAIN_GRAPHQL_URL


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
                    "metadata": {"name": "Request form"},
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
                    "metadata": {"name": "Request form"},
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

    result = await service.list_portals(EXAMPLE_ORG_UUID)

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

    await service.list_portals(EXAMPLE_OTHER_ORG_UUID)

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    assert query_used is LIST_PORTALS_QUERY
    assert variables == {
        "org_uuid": EXAMPLE_OTHER_ORG_UUID,
        "filterBySubType": "portal",
    }


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

    await service.list_portals(EXAMPLE_ORG_UUID, search_term="intake")

    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    assert query_used is LIST_PORTALS_QUERY
    assert variables == {
        "org_uuid": EXAMPLE_ORG_UUID,
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

    result = await service.list_portals(EXAMPLE_ORG_UUID)

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

    await service.list_portals(EXAMPLE_ORG_UUID)

    service._graphql_client.execute_query.assert_not_called()
    _, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables["org_uuid"] == EXAMPLE_ORG_UUID


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
        return_value={"organization": {"uuid": EXAMPLE_ORG_UUID}}
    )

    await service.list_portals(EXAMPLE_NUMERIC_ORG_ID)

    service._graphql_client.execute_query.assert_called_once_with(
        RESOLVE_ORGANIZATION_UUID_QUERY,
        {"id": EXAMPLE_NUMERIC_ORG_ID},
    )
    _, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables["org_uuid"] == EXAMPLE_ORG_UUID


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_portals_accepts_int_org_id(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Integer org ids coerce to string before resolve and Interfaces list."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"interfaces": {"edges": []}},
    )
    service._graphql_client.execute_query = AsyncMock(
        return_value={"organization": {"uuid": EXAMPLE_ORG_UUID}}
    )

    await service.list_portals(int(EXAMPLE_NUMERIC_ORG_ID))

    service._graphql_client.execute_query.assert_called_once_with(
        RESOLVE_ORGANIZATION_UUID_QUERY,
        {"id": EXAMPLE_NUMERIC_ORG_ID},
    )
    _, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables["org_uuid"] == EXAMPLE_ORG_UUID


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
        await service.list_portals(EXAMPLE_NUMERIC_ORG_ID)


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


_portal_queries_module = importlib.import_module("pipefy_sdk.queries.portal_queries")


def _portal_mutation_constant(name: str):
    """Return the portal mutation constant when exported; else None (TDD placeholder)."""
    return getattr(_portal_queries_module, name, None)


def _assert_interfaces_mutation_query(query_used: object, constant_name: str) -> None:
    """Assert Interfaces mutation document matches the expected portal_queries constant."""
    expected = _portal_mutation_constant(constant_name)
    if expected is not None:
        assert query_used is expected
    else:
        operation_snippets = {
            "FIND_OR_CREATE_PORTAL_MUTATION": "findOrCreateInterfaceByTemplate",
            "UPDATE_INTERFACE_MUTATION": "updateInterface",
            "DELETE_INTERFACE_MUTATION": "deleteInterface",
            "CREATE_PAGE_MUTATION": "createPage",
            "UPDATE_PAGE_MUTATION": "updatePage",
            "DELETE_PAGE_MUTATION": "deletePage",
            "SORT_PAGES_MUTATION": "sortPages",
            "UPDATE_PAGE_LAYOUT_MUTATION": "updatePageLayout",
            "CREATE_ELEMENT_MUTATION": "createElement",
            "UPDATE_ELEMENT_MUTATION": "updateElement",
            "DELETE_ELEMENT_MUTATION": "deleteElement",
            "DUPLICATE_ELEMENT_MUTATION": "duplicateElement",
            "CREATE_SUB_PORTAL_MUTATION": "createSubPortal",
        }
        assert operation_snippets[constant_name] in str(query_used)


try:
    _portal_internal_queries_module = importlib.import_module(
        "pipefy_sdk.queries.portal_internal_queries"
    )
except ModuleNotFoundError:
    _portal_internal_queries_module = None


def _portal_internal_mutation_constant(name: str):
    """Return the internal_api mutation constant when exported; else None (TDD)."""
    if _portal_internal_queries_module is None:
        return None
    return getattr(_portal_internal_queries_module, name, None)


def _assert_internal_mutation_query(query_used: object, constant_name: str) -> None:
    """Assert internal_api mutation document matches the expected constant."""
    expected = _portal_internal_mutation_constant(constant_name)
    if expected is not None:
        assert query_used is expected
    else:
        operation_snippets = {
            "UPDATE_SUB_PORTAL_ELEMENT_MUTATION": "updateSubPortalElement",
            "DELETE_SUB_PORTAL_ELEMENT_MUTATION": "deleteSubPortalElement",
            "DELETE_SUB_PORTAL_INTERFACE_MUTATION": "deleteSubPortalInterface",
        }
        assert operation_snippets[constant_name] in str(query_used)


def _make_portal_service_with_clients(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
    *,
    interfaces_return: dict | None = None,
    internal_return: dict | None = None,
) -> tuple[PortalService, MagicMock, MagicMock]:
    """PortalService with mocked Interfaces and internal_api clients."""
    mock_internal = _mock_internal_api_client()
    if internal_return is not None:
        mock_internal.execute_query = AsyncMock(return_value=internal_return)
    service = PortalService(
        settings=mock_settings,
        auth=mock_auth,
        internal_api_client=mock_internal,
    )
    interfaces_execute = AsyncMock()
    if interfaces_return is not None:
        interfaces_execute.return_value = interfaces_return
    service._interfaces_client.execute_query = interfaces_execute
    return service, service._interfaces_client, mock_internal


_CREATE_PORTAL_GRAPHQL_INTERFACE = {
    "id": "portal-created-uuid",
    "name": "Org Portal",
    "visibility": "internal",
    "subType": "portal",
}

_CREATE_PORTAL_RESPONSE = {
    "findOrCreateInterfaceByTemplate": {
        "interface": _CREATE_PORTAL_GRAPHQL_INTERFACE,
    }
}

_PERMISSION_DENIED_ERROR = TransportQueryError(
    "GraphQL request failed",
    errors=[
        {
            "message": "Permission Denied",
            "extensions": {"code": "PERMISSION_DENIED"},
        }
    ],
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_resolves_numeric_org_and_calls_find_or_create_template(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """create_portal resolves numeric org id then findOrCreateInterfaceByTemplate."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_PORTAL_RESPONSE,
    )
    service._graphql_client.execute_query = AsyncMock(
        return_value={"organization": {"uuid": EXAMPLE_ORG_UUID}}
    )

    result = await service.create_portal(EXAMPLE_NUMERIC_ORG_ID)

    service._graphql_client.execute_query.assert_called_once_with(
        RESOLVE_ORGANIZATION_UUID_QUERY,
        {"id": EXAMPLE_NUMERIC_ORG_ID},
    )
    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "FIND_OR_CREATE_PORTAL_MUTATION")
    assert variables == {"input": {"orgUuid": EXAMPLE_ORG_UUID, "subType": "portal"}}
    assert result["uuid"] == "portal-created-uuid"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_uuid_org_skips_resolve(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """UUID-shaped org identifiers skip resolve before findOrCreate mutation."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_PORTAL_RESPONSE,
    )
    service._graphql_client.execute_query = AsyncMock()

    await service.create_portal(EXAMPLE_ORG_UUID)

    service._graphql_client.execute_query.assert_not_called()
    _, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables == {"input": {"orgUuid": EXAMPLE_ORG_UUID, "subType": "portal"}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_idempotent_returns_same_interface_uuid(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Second create_portal call returns the same interface uuid (idempotent)."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_PORTAL_RESPONSE,
    )

    first = await service.create_portal(EXAMPLE_ORG_UUID)
    second = await service.create_portal(EXAMPLE_ORG_UUID)

    assert first["uuid"] == second["uuid"] == "portal-created-uuid"
    assert service._interfaces_client.execute_query.call_count == 2
    for call in service._interfaces_client.execute_query.call_args_list:
        _, variables = call[0]
        assert variables == {
            "input": {"orgUuid": EXAMPLE_ORG_UUID, "subType": "portal"}
        }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_portal_passes_only_set_fields_under_input(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """update_portal sends snake_case interface_uuid and only provided fields."""
    update_response = {
        "updateInterface": {
            "interface": {**_CREATE_PORTAL_GRAPHQL_INTERFACE, "name": "Renamed"},
        }
    }
    service = _make_interfaces_service(mock_settings, mock_auth, update_response)

    await service.update_portal("portal-created-uuid", name="Renamed")

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "UPDATE_INTERFACE_MUTATION")
    assert variables == {
        "input": {"interface_uuid": "portal-created-uuid", "name": "Renamed"}
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_portal_omits_unset_optional_fields(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Unset optional fields are not included in updateInterface input."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {
            "updateInterface": {
                "interface": {
                    **_CREATE_PORTAL_GRAPHQL_INTERFACE,
                    "visibility": "public",
                }
            }
        },
    )

    await service.update_portal(
        "portal-created-uuid",
        visibility="public",
    )

    _, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables == {
        "input": {
            "interface_uuid": "portal-created-uuid",
            "visibility": "public",
        }
    }
    assert "name" not in variables["input"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_portal_rejects_invalid_visibility_before_graphql(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Invalid visibility values raise ValidationError before any GraphQL call."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"updateInterface": {"interface": _CREATE_PORTAL_GRAPHQL_INTERFACE}},
    )

    with pytest.raises(ValidationError):
        await service.update_portal(
            "portal-created-uuid",
            visibility="public_visibility",
        )

    service._interfaces_client.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_portal_serializes_all_fields_with_camel_case_aliases(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """update_portal sends displayPipefyHeader and omits unset fields."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {
            "updateInterface": {
                "interface": {
                    **_CREATE_PORTAL_GRAPHQL_INTERFACE,
                    "name": "Full Update",
                    "visibility": "public",
                }
            }
        },
    )

    await service.update_portal(
        "portal-created-uuid",
        name="Full Update",
        visibility="public",
        color="#aabbcc",
        icon="layout",
        display_pipefy_header=True,
    )

    _, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables == {
        "input": {
            "interface_uuid": "portal-created-uuid",
            "name": "Full Update",
            "visibility": "public",
            "color": "#aabbcc",
            "icon": "layout",
            "displayPipefyHeader": True,
        }
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_portal_calls_delete_interface_with_interface_uuid(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """delete_portal uses deleteInterface with snake_case input.interface_uuid."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"deleteInterface": {"success": True}},
    )

    result = await service.delete_portal("portal-to-delete")

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "DELETE_INTERFACE_MUTATION")
    assert variables == {"input": {"interface_uuid": "portal-to-delete"}}
    assert result == {"deleteInterface": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_permission_denied_surfaces_actionable_message(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """PERMISSION_DENIED from Interfaces maps to portal permission guidance."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_PORTAL_RESPONSE,
    )
    service._interfaces_client.execute_query = AsyncMock(
        side_effect=_PERMISSION_DENIED_ERROR
    )

    with pytest.raises(PortalPermissionError, match=r"(create_portal|manage_portals)"):
        await service.create_portal(EXAMPLE_ORG_UUID)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_portal_permission_denied_surfaces_actionable_message(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """PERMISSION_DENIED on update maps to portal permission guidance."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"updateInterface": {"interface": _CREATE_PORTAL_GRAPHQL_INTERFACE}},
    )
    service._interfaces_client.execute_query = AsyncMock(
        side_effect=_PERMISSION_DENIED_ERROR
    )

    with pytest.raises(PortalPermissionError, match=r"(create_portal|manage_portals)"):
        await service.update_portal("portal-created-uuid", name="Renamed")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_portal_permission_denied_surfaces_actionable_message(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """PERMISSION_DENIED on delete maps to portal permission guidance."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"deleteInterface": {"success": True}},
    )
    service._interfaces_client.execute_query = AsyncMock(
        side_effect=_PERMISSION_DENIED_ERROR
    )

    with pytest.raises(PortalPermissionError, match=r"(create_portal|manage_portals)"):
        await service.delete_portal("portal-to-delete")


_INTERFACE_UUID = "portal-uuid-1"
_PAGE_ID = "page-uuid-1"
_PAGE_ID_2 = "page-uuid-2"
_PAGE_TITLE = "Portal Home"

_CREATE_PAGE_GRAPHQL = {
    "id": _PAGE_ID,
    "title": _PAGE_TITLE,
    "elements": [{"id": "el-1", "type": "text"}],
}

_CREATE_PAGE_RESPONSE = {
    "createPage": {"page": _CREATE_PAGE_GRAPHQL},
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_page_calls_create_page_with_interface_uuid_and_title(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """create_portal_page uses createPage with interface_uuid and title."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_PAGE_RESPONSE,
    )

    result = await service.create_portal_page(_INTERFACE_UUID, _PAGE_TITLE)

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "CREATE_PAGE_MUTATION")
    assert variables == {
        "input": {"interface_uuid": _INTERFACE_UUID, "title": _PAGE_TITLE}
    }
    assert result["uuid"] == _PAGE_ID
    assert result["title"] == _PAGE_TITLE


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_page_forwards_optional_fields(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Optional createPage fields are included when provided."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_PAGE_RESPONSE,
    )

    await service.create_portal_page(
        _INTERFACE_UUID,
        _PAGE_TITLE,
        description="Landing copy",
        index=1,
    )

    _, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables == {
        "input": {
            "interface_uuid": _INTERFACE_UUID,
            "title": _PAGE_TITLE,
            "description": "Landing copy",
            "index": 1,
        }
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_portal_page_calls_update_page_with_required_ids(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """update_portal_page uses updatePage with interface_uuid and page_id."""
    update_response = {
        "updatePage": {
            "page": {**_CREATE_PAGE_GRAPHQL, "title": "Renamed Page"},
        }
    }
    service = _make_interfaces_service(mock_settings, mock_auth, update_response)

    result = await service.update_portal_page(
        _INTERFACE_UUID,
        _PAGE_ID,
        title="Renamed Page",
    )

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "UPDATE_PAGE_MUTATION")
    assert variables == {
        "input": {
            "interface_uuid": _INTERFACE_UUID,
            "page_id": _PAGE_ID,
            "title": "Renamed Page",
        }
    }
    assert result["title"] == "Renamed Page"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_portal_page_omits_unset_optional_fields(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Unset optional updatePage fields are not sent to GraphQL."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"updatePage": {"page": _CREATE_PAGE_GRAPHQL}},
    )

    await service.update_portal_page(
        _INTERFACE_UUID,
        _PAGE_ID,
        description="Only description changed",
    )

    _, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables == {
        "input": {
            "interface_uuid": _INTERFACE_UUID,
            "page_id": _PAGE_ID,
            "description": "Only description changed",
        }
    }
    assert "title" not in variables["input"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_portal_page_calls_delete_page_with_interface_and_page_ids(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """delete_portal_page uses deletePage with interface_uuid and page_id."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"deletePage": {"success": True}},
    )

    result = await service.delete_portal_page(_INTERFACE_UUID, _PAGE_ID)

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "DELETE_PAGE_MUTATION")
    assert variables == {
        "input": {"interface_uuid": _INTERFACE_UUID, "page_id": _PAGE_ID}
    }
    assert result == {"deletePage": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sort_portal_pages_calls_sort_pages_with_page_ids_list(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """sort_portal_pages uses sortPages with interface_uuid and page_ids."""
    page_ids = [_PAGE_ID_2, _PAGE_ID]
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"sortPages": {"success": True}},
    )

    result = await service.sort_portal_pages(_INTERFACE_UUID, page_ids)

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "SORT_PAGES_MUTATION")
    assert variables == {
        "input": {"interface_uuid": _INTERFACE_UUID, "page_ids": page_ids}
    }
    assert result == {"sortPages": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_portal_page_layout_does_not_send_interface_uuid(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """update_portal_page_layout uses updatePageLayout with page_id and layout only."""
    layout = {"rows": [{"columns": [{"width": 12}]}]}
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"updatePageLayout": {"success": True}},
    )

    result = await service.update_portal_page_layout(_PAGE_ID, layout)

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "UPDATE_PAGE_LAYOUT_MUTATION")
    assert variables == {
        "input": {
            "page_id": _PAGE_ID,
            "layout": json.dumps(layout, separators=(",", ":"), ensure_ascii=False),
        }
    }
    assert "interface_uuid" not in variables["input"]
    assert result == {"updatePageLayout": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_page_permission_denied_surfaces_actionable_message(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """PERMISSION_DENIED on createPage maps to portal permission guidance."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_PAGE_RESPONSE,
    )
    service._interfaces_client.execute_query = AsyncMock(
        side_effect=_PERMISSION_DENIED_ERROR
    )

    with pytest.raises(PortalPermissionError, match=r"(create_portal|manage_portals)"):
        await service.create_portal_page(_INTERFACE_UUID, _PAGE_TITLE)


_ELEMENT_ID = "el-uuid-1"
_FORMS_METADATA = {"name": "Request form"}
_FORMS_DATA_SOURCES = [{"repo_uuid": EXAMPLE_PIPE_REPO_ID}]

_CREATE_ELEMENT_GRAPHQL = {
    "id": _ELEMENT_ID,
    "type": "forms",
    "metadata": _FORMS_METADATA,
}

_CREATE_ELEMENT_RESPONSE = {
    "createElement": {"element": _CREATE_ELEMENT_GRAPHQL},
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_element_calls_create_element_with_validated_input(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """create_portal_element validates via CreatePortalElementInput then createElement."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_ELEMENT_RESPONSE,
    )

    await service.create_portal_element(
        _PAGE_ID,
        type="forms",
        metadata=_FORMS_METADATA,
        data_sources=_FORMS_DATA_SOURCES,
    )

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "CREATE_ELEMENT_MUTATION")
    assert variables == {
        "input": {
            "page_id": _PAGE_ID,
            "type": "forms",
            "metadata": json.dumps(
                _FORMS_METADATA, separators=(",", ":"), ensure_ascii=False
            ),
            "data_sources": [{"repoId": EXAMPLE_PIPE_REPO_ID, "fieldKeys": []}],
        }
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_element_always_sends_empty_data_sources_for_link(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Link creates must send data_sources: [] so Pipefy does not receive null."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_ELEMENT_RESPONSE,
    )
    link_metadata = {"linkName": "Test", "linkUrl": "https://example.com"}

    await service.create_portal_element(_PAGE_ID, type="link", metadata=link_metadata)

    _query_used, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables["input"]["data_sources"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_element_logs_warning_for_unrecognized_data_source_keys(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid data_sources entries are skipped with a warning (e.g. LLM-guessed pipe_id)."""
    caplog.set_level(logging.WARNING, logger="pipefy_sdk.services.portal_service")
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_ELEMENT_RESPONSE,
    )

    await service.create_portal_element(
        _PAGE_ID,
        type="forms",
        metadata=_FORMS_METADATA,
        data_sources=[{"pipe_id": "123"}],
    )

    assert any("Skipping portal data_sources" in r.message for r in caplog.records)
    _query_used, variables = service._interfaces_client.execute_query.call_args[0]
    assert variables["input"]["data_sources"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_element_graphql_error_is_not_portal_permission_error(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Non-permission Interfaces failures must not be wrapped as PortalPermissionError."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_ELEMENT_RESPONSE,
    )
    service._interfaces_client.execute_query = AsyncMock(
        side_effect=TransportQueryError(
            "invalid",
            errors=[{"message": "Variable $input was provided invalid value"}],
        )
    )

    with pytest.raises(TransportQueryError):
        await service.create_portal_element(
            _PAGE_ID,
            type="link",
            metadata={"linkName": "Test", "linkUrl": "https://example.com"},
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_portal_element_rejects_invalid_metadata_before_graphql(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """CreatePortalElementInput validation must run before execute_query."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        _CREATE_ELEMENT_RESPONSE,
    )

    with pytest.raises(ValidationError, match="name"):
        await service.create_portal_element(
            _PAGE_ID,
            type="forms",
            metadata={},
        )

    service._interfaces_client.execute_query.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_portal_element_calls_update_element_with_full_metadata(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """update_portal_element sends element_id, page_id, and full metadata replace."""
    link_metadata = {
        "linkUrl": "https://example.com/pipefy",
        "linkName": "Open",
    }
    update_response = {"updateElement": {"success": True}}
    service = _make_interfaces_service(mock_settings, mock_auth, update_response)

    result = await service.update_portal_element(
        _ELEMENT_ID,
        _PAGE_ID,
        type="link",
        metadata=link_metadata,
    )

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "UPDATE_ELEMENT_MUTATION")
    assert variables == {
        "input": {
            "element_id": _ELEMENT_ID,
            "page_id": _PAGE_ID,
            "metadata": json.dumps(
                link_metadata, separators=(",", ":"), ensure_ascii=False
            ),
            "data_sources": [],
        }
    }
    assert result["metadata"]["linkUrl"] == "https://example.com/pipefy"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_portal_element_calls_delete_element_with_ids(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """delete_portal_element uses deleteElement with element_id and page_id."""
    service = _make_interfaces_service(
        mock_settings,
        mock_auth,
        {"deleteElement": {"success": True}},
    )

    result = await service.delete_portal_element(_ELEMENT_ID, _PAGE_ID)

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "DELETE_ELEMENT_MUTATION")
    assert variables == {
        "input": {"element_id": _ELEMENT_ID, "page_id": _PAGE_ID},
    }
    assert result == {"deleteElement": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_duplicate_portal_element_sends_camel_case_duplicate_input(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """duplicateElement input uses elementUuid, interfaceUuid, pageUuid (camelCase)."""
    dup_response = {
        "duplicateElement": {
            "element": {"id": "el-copy", "type": "text", "metadata": {}},
        }
    }
    service = _make_interfaces_service(mock_settings, mock_auth, dup_response)

    result = await service.duplicate_portal_element(
        element_id=_ELEMENT_ID,
        portal_uuid=_INTERFACE_UUID,
        page_id=_PAGE_ID,
    )

    service._interfaces_client.execute_query.assert_called_once()
    query_used, variables = service._interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "DUPLICATE_ELEMENT_MUTATION")
    assert variables == {
        "input": {
            "elementUuid": _ELEMENT_ID,
            "interfaceUuid": _INTERFACE_UUID,
            "pageUuid": _PAGE_ID,
        }
    }
    assert result["uuid"] == "el-copy"


_MAIN_PORTAL_UUID = "portal-main-uuid"
_SUB_PORTAL_UUID = "sub-portal-uuid"
_FORMS_ELEMENT_ID = "forms-element-uuid"
_SUB_PORTAL_NAME = "Intake sub-portal"

_CREATE_SUB_PORTAL_GRAPHQL = {
    "id": _SUB_PORTAL_UUID,
    "name": _SUB_PORTAL_NAME,
}

_CREATE_SUB_PORTAL_RESPONSE = {
    "createSubPortal": {"subPortal": _CREATE_SUB_PORTAL_GRAPHQL},
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_sub_portal_calls_create_sub_portal_on_interfaces(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """create_sub_portal uses Interfaces createSubPortal with mainPortalUuid."""
    service, interfaces_client, internal_client = _make_portal_service_with_clients(
        mock_settings,
        mock_auth,
        interfaces_return=_CREATE_SUB_PORTAL_RESPONSE,
    )

    result = await service.create_sub_portal(_MAIN_PORTAL_UUID, name=_SUB_PORTAL_NAME)

    interfaces_client.execute_query.assert_called_once()
    internal_client.execute_query.assert_not_called()
    query_used, variables = interfaces_client.execute_query.call_args[0]
    _assert_interfaces_mutation_query(query_used, "CREATE_SUB_PORTAL_MUTATION")
    assert variables == {
        "input": {
            "mainPortalUuid": _MAIN_PORTAL_UUID,
            "name": _SUB_PORTAL_NAME,
        }
    }
    assert result["uuid"] == _SUB_PORTAL_UUID
    assert result["name"] == _SUB_PORTAL_NAME


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_sub_portal_omits_name_when_not_provided(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Optional name is omitted from createSubPortal input when None."""
    service, interfaces_client, _internal_client = _make_portal_service_with_clients(
        mock_settings,
        mock_auth,
        interfaces_return=_CREATE_SUB_PORTAL_RESPONSE,
    )

    await service.create_sub_portal(_MAIN_PORTAL_UUID)

    _, variables = interfaces_client.execute_query.call_args[0]
    assert variables == {"input": {"mainPortalUuid": _MAIN_PORTAL_UUID}}
    assert "name" not in variables["input"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_sub_portal_element_routes_through_internal_api(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """update_sub_portal_element uses internal_api updateSubPortalElement."""
    internal_response = {"updateSubPortalElement": {"success": True}}
    service, interfaces_client, internal_client = _make_portal_service_with_clients(
        mock_settings,
        mock_auth,
        internal_return=internal_response,
    )

    result = await service.update_sub_portal_element(
        _MAIN_PORTAL_UUID,
        _FORMS_ELEMENT_ID,
        _SUB_PORTAL_UUID,
    )

    interfaces_client.execute_query.assert_not_called()
    internal_client.execute_query.assert_called_once()
    query_used, variables = internal_client.execute_query.call_args[0]
    _assert_internal_mutation_query(query_used, "UPDATE_SUB_PORTAL_ELEMENT_MUTATION")
    assert variables == {
        "input": {
            "portalUuid": _MAIN_PORTAL_UUID,
            "elementId": _FORMS_ELEMENT_ID,
            "subPortalUuid": _SUB_PORTAL_UUID,
        }
    }
    assert result == internal_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_publish_sub_portal_delegates_to_update_sub_portal_element(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """publish_sub_portal wires subPortalUuid via updateSubPortalElement (not createElement)."""
    internal_response = {"updateSubPortalElement": {"success": True}}
    service, interfaces_client, internal_client = _make_portal_service_with_clients(
        mock_settings,
        mock_auth,
        internal_return=internal_response,
    )

    result = await service.publish_sub_portal(
        _MAIN_PORTAL_UUID,
        _FORMS_ELEMENT_ID,
        _SUB_PORTAL_UUID,
    )

    interfaces_client.execute_query.assert_not_called()
    internal_client.execute_query.assert_called_once()
    _, variables = internal_client.execute_query.call_args[0]
    assert variables["input"]["subPortalUuid"] == _SUB_PORTAL_UUID
    assert result == internal_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unpublish_sub_portal_sends_null_sub_portal_uuid(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """unpublish_sub_portal clears subPortalUuid (null); 6.7 integration confirms detach."""
    service, interfaces_client, internal_client = _make_portal_service_with_clients(
        mock_settings,
        mock_auth,
        internal_return={"updateSubPortalElement": {"success": True}},
    )

    await service.unpublish_sub_portal(_MAIN_PORTAL_UUID, _FORMS_ELEMENT_ID)

    interfaces_client.execute_query.assert_not_called()
    internal_client.execute_query.assert_called_once()
    _, variables = internal_client.execute_query.call_args[0]
    assert variables == {
        "input": {
            "portalUuid": _MAIN_PORTAL_UUID,
            "elementId": _FORMS_ELEMENT_ID,
            "subPortalUuid": None,
        }
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_sub_portal_element_routes_through_internal_api(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """delete_sub_portal_element uses internal_api deleteSubPortalElement."""
    internal_response = {"deleteSubPortalElement": {"success": True}}
    service, interfaces_client, internal_client = _make_portal_service_with_clients(
        mock_settings,
        mock_auth,
        internal_return=internal_response,
    )

    result = await service.delete_sub_portal_element(
        _MAIN_PORTAL_UUID,
        _FORMS_ELEMENT_ID,
    )

    interfaces_client.execute_query.assert_not_called()
    internal_client.execute_query.assert_called_once()
    query_used, variables = internal_client.execute_query.call_args[0]
    _assert_internal_mutation_query(query_used, "DELETE_SUB_PORTAL_ELEMENT_MUTATION")
    assert variables == {
        "input": {
            "portalUuid": _MAIN_PORTAL_UUID,
            "elementId": _FORMS_ELEMENT_ID,
        }
    }
    assert result == internal_response


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_sub_portal_calls_delete_sub_portal_interface(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """delete_sub_portal removes the sub-portal entity via deleteSubPortalInterface."""
    internal_response = {"deleteSubPortalInterface": {"success": True}}
    service, interfaces_client, internal_client = _make_portal_service_with_clients(
        mock_settings,
        mock_auth,
        internal_return=internal_response,
    )

    result = await service.delete_sub_portal(_SUB_PORTAL_UUID)

    interfaces_client.execute_query.assert_not_called()
    internal_client.execute_query.assert_called_once()
    query_used, variables = internal_client.execute_query.call_args[0]
    _assert_internal_mutation_query(query_used, "DELETE_SUB_PORTAL_INTERFACE_MUTATION")
    assert variables == {"input": {"uuid": _SUB_PORTAL_UUID}}
    assert result == internal_response


_INTERNAL_API_PERMISSION_DENIED_VALUE_ERROR = ValueError(
    "User does not have permission to manage portals "
    "[code=PERMISSION_DENIED] [correlation_id=abc-123]"
)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "call_args"),
    [
        (
            "update_sub_portal_element",
            (_MAIN_PORTAL_UUID, _FORMS_ELEMENT_ID, _SUB_PORTAL_UUID),
        ),
        (
            "publish_sub_portal",
            (_MAIN_PORTAL_UUID, _FORMS_ELEMENT_ID, _SUB_PORTAL_UUID),
        ),
        (
            "unpublish_sub_portal",
            (_MAIN_PORTAL_UUID, _FORMS_ELEMENT_ID),
        ),
        (
            "delete_sub_portal_element",
            (_MAIN_PORTAL_UUID, _FORMS_ELEMENT_ID),
        ),
        ("delete_sub_portal", (_SUB_PORTAL_UUID,)),
    ],
)
async def test_sub_portal_internal_api_permission_denied_surfaces_actionable_message(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
    method_name: str,
    call_args: tuple[str, ...],
) -> None:
    """PERMISSION_DENIED from internal_api maps to portal permission guidance."""
    service, _interfaces_client, internal_client = _make_portal_service_with_clients(
        mock_settings,
        mock_auth,
    )
    internal_client.execute_query = AsyncMock(
        side_effect=_INTERNAL_API_PERMISSION_DENIED_VALUE_ERROR
    )

    with pytest.raises(PortalPermissionError, match=r"(create_portal|manage_portals)"):
        await getattr(service, method_name)(*call_args)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sub_portal_internal_api_non_permission_value_error_propagates(
    mock_settings: PipefySettings,
    mock_auth: OAuth2ClientCredentials,
) -> None:
    """Non-permission internal_api ValueError must not become PortalPermissionError."""
    service, _interfaces_client, internal_client = _make_portal_service_with_clients(
        mock_settings,
        mock_auth,
    )
    bad_request = ValueError("Bad request [code=BAD_REQUEST] [correlation_id=abc-123]")
    internal_client.execute_query = AsyncMock(side_effect=bad_request)

    with pytest.raises(ValueError, match="Bad request"):
        await service.update_sub_portal_element(
            _MAIN_PORTAL_UUID,
            _FORMS_ELEMENT_ID,
            _SUB_PORTAL_UUID,
        )
