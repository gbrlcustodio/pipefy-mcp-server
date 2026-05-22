"""Service for Pipefy portal operations (Interfaces + internal_api routing)."""

from __future__ import annotations

from typing import Any

from gql.transport.exceptions import TransportQueryError
from httpx import Auth

from pipefy_sdk.base_client import BasePipefyClient, unwrap_relay_connection_nodes
from pipefy_sdk.models.portal import UpdatePortalInput
from pipefy_sdk.queries.portal_queries import (
    DELETE_INTERFACE_MUTATION,
    FIND_OR_CREATE_PORTAL_MUTATION,
    GET_PORTAL_QUERY,
    LIST_PORTALS_QUERY,
    UPDATE_INTERFACE_MUTATION,
)
from pipefy_sdk.services.internal_api_client import InternalApiClient
from pipefy_sdk.settings import PipefySettings
from pipefy_sdk.utils.organization_identifiers import resolve_organization_uuid


def _with_uuid_alias(record: dict[str, Any]) -> dict[str, Any]:
    """Expose GraphQL ``id`` as ``uuid`` in portal payloads."""
    if "id" in record and "uuid" not in record:
        return {**record, "uuid": record["id"]}
    return record


_PORTAL_VISIBILITY_VALUES = frozenset({"internal", "private", "public"})


def _map_portal_permission_error(exc: TransportQueryError) -> ValueError:
    """Turn PERMISSION_DENIED GraphQL errors into actionable portal guidance."""
    for err in exc.errors or []:
        if not isinstance(err, dict):
            continue
        extensions = err.get("extensions") or {}
        if extensions.get("code") == "PERMISSION_DENIED":
            return ValueError(
                "Permission denied. Request organization permissions such as "
                "`create_portal` or `manage_portals` from your admin."
            )
    return ValueError(str(exc))


async def _execute_interfaces_query_with_portal_errors(
    execute: Any,
    query: Any,
    variables: dict[str, Any],
) -> dict[str, Any]:
    """Run an Interfaces operation and map portal permission failures."""
    try:
        return await execute(query, variables)
    except TransportQueryError as exc:
        raise _map_portal_permission_error(exc) from exc


def _normalize_portal_detail(portal: dict[str, Any]) -> dict[str, Any]:
    """Normalize a ``PortalInterface`` detail payload from the Interfaces schema."""
    pages = portal.get("pages") or []
    normalized_pages = []
    for page in pages:
        page_record = _with_uuid_alias(page)
        elements = [_with_uuid_alias(element) for element in page.get("elements") or []]
        normalized_pages.append({**page_record, "elements": elements})
    sub_portals = [
        _with_uuid_alias(sub_portal) for sub_portal in portal.get("subPortals") or []
    ]
    return {
        **_with_uuid_alias(portal),
        "pages": normalized_pages,
        "subPortals": sub_portals,
    }


class PortalService:
    """GraphQL operations for Pipefy portals across multiple endpoints.

    Composes two ``BasePipefyClient`` instances (Interfaces + public GraphQL) instead
    of inheriting because the Interfaces schema lives on a separate endpoint. When
    constructing outside ``PipefyClient``, pass a shared ``auth`` to both clients so
    OAuth token caching is not duplicated.
    """

    def __init__(
        self,
        settings: PipefySettings,
        auth: Auth | None = None,
        *,
        internal_api_client: InternalApiClient | None = None,
    ) -> None:
        """Wire clients for Interfaces schema and optional internal_api mutations.

        Args:
            settings: Pipefy endpoints and credentials.
            auth: Shared OAuth or bearer auth for GraphQL transports.
            internal_api_client: Client for sub-portal element wiring mutations.
        """
        interfaces_settings = settings.model_copy(
            update={"graphql_url": settings.interfaces_graphql_url}
        )
        self._interfaces_client = BasePipefyClient(
            settings=interfaces_settings,
            auth=auth,
        )
        self._graphql_client = BasePipefyClient(
            settings=settings,
            auth=auth,
        )
        self._internal_api_client = internal_api_client

    async def execute_interfaces_query(
        self,
        query: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a GraphQL query or mutation on the Interfaces schema.

        Args:
            query: GraphQL document string.
            variables: Variable map for the operation.
        """
        return await self._interfaces_client.execute_query(query, variables)

    async def execute_internal_api_query(
        self,
        query: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a GraphQL query or mutation on the internal_api endpoint.

        Args:
            query: GraphQL document string.
            variables: Variable map for the operation.

        Raises:
            ValueError: When no internal API client was injected.
        """
        if self._internal_api_client is None:
            msg = "Internal API client is not configured."
            raise ValueError(msg)
        return await self._internal_api_client.execute_query(query, variables)

    async def list_portals(
        self,
        organization_uuid: str | int,
        search_term: str | None = None,
    ) -> list[dict[str, Any]]:
        """List portals for an organization via the Interfaces schema.

        Args:
            organization_uuid: Organization UUID, or numeric organization id.
            search_term: Optional name filter forwarded as ``searchTerm``.
        """
        resolved_org_uuid = await resolve_organization_uuid(
            self._graphql_client.execute_query,
            organization_uuid,
        )
        variables: dict[str, Any] = {
            "org_uuid": resolved_org_uuid,
            "filterBySubType": "portal",
        }
        if search_term is not None:
            variables["searchTerm"] = search_term
        data = await self.execute_interfaces_query(LIST_PORTALS_QUERY, variables)
        nodes = unwrap_relay_connection_nodes(data.get("interfaces"))
        return [_with_uuid_alias(node) for node in nodes]

    async def get_portal(self, portal_uuid: str) -> dict[str, Any]:
        """Fetch a portal by UUID including pages, elements, and sub-portals.

        Args:
            portal_uuid: Portal interface UUID.

        Raises:
            ValueError: When ``portalInterface`` resolves to null.
        """
        data = await self.execute_interfaces_query(
            GET_PORTAL_QUERY, {"uuid": portal_uuid}
        )
        portal = data.get("portalInterface")
        if portal is None:
            msg = f"Portal '{portal_uuid}' was not found."
            raise ValueError(msg)
        return _normalize_portal_detail(portal)

    async def create_portal(self, organization_uuid: str | int) -> dict[str, Any]:
        """Create or fetch the organization's main portal (idempotent template flow).

        Args:
            organization_uuid: Organization UUID or numeric organization id.

        Returns:
            Portal interface summary with ``uuid`` alias for ``id``.
        """
        resolved_org_uuid = await resolve_organization_uuid(
            self._graphql_client.execute_query,
            organization_uuid,
        )
        data = await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            FIND_OR_CREATE_PORTAL_MUTATION,
            {"input": {"orgUuid": resolved_org_uuid, "subType": "portal"}},
        )
        interface = (data.get("findOrCreateInterfaceByTemplate") or {}).get("interface")
        if not isinstance(interface, dict):
            msg = "findOrCreateInterfaceByTemplate returned no interface."
            raise ValueError(msg)
        return _with_uuid_alias(interface)

    async def update_portal(
        self,
        interface_uuid: str,
        *,
        name: str | None = None,
        visibility: str | None = None,
        color: str | None = None,
        icon: str | None = None,
        display_pipefy_header: bool | None = None,
    ) -> dict[str, Any]:
        """Update portal metadata on the Interfaces schema.

        Args:
            interface_uuid: Portal interface UUID.
            name: Optional display name.
            visibility: ``internal``, ``private``, or ``public``.
            color: Optional theme color.
            icon: Optional icon identifier.
            display_pipefy_header: Whether to show the Pipefy header.
        """
        if visibility is not None and visibility not in _PORTAL_VISIBILITY_VALUES:
            msg = (
                f"Invalid visibility {visibility!r}. "
                "Must be one of: internal, private, public."
            )
            raise ValueError(msg)
        portal_input = UpdatePortalInput(
            interface_uuid=interface_uuid,
            name=name,
            visibility=visibility,  # type: ignore[arg-type]
            color=color,
            icon=icon,
            display_pipefy_header=display_pipefy_header,
        )
        variables = {
            "input": portal_input.model_dump(exclude_unset=True, exclude_none=True)
        }
        data = await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            UPDATE_INTERFACE_MUTATION,
            variables,
        )
        interface = (data.get("updateInterface") or {}).get("interface")
        if not isinstance(interface, dict):
            msg = "updateInterface returned no interface."
            raise ValueError(msg)
        return _with_uuid_alias(interface)

    async def delete_portal(self, interface_uuid: str) -> dict[str, Any]:
        """Delete a portal interface (irreversible).

        Args:
            interface_uuid: Portal interface UUID.
        """
        return await _execute_interfaces_query_with_portal_errors(
            self.execute_interfaces_query,
            DELETE_INTERFACE_MUTATION,
            {"input": {"interface_uuid": interface_uuid}},
        )
