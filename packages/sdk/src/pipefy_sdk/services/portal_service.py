"""Service for Pipefy portal operations (Interfaces + internal_api routing)."""

from __future__ import annotations

from typing import Any

from httpx import Auth

from pipefy_sdk.base_client import BasePipefyClient, unwrap_relay_connection_nodes
from pipefy_sdk.queries.observability_queries import RESOLVE_ORGANIZATION_UUID_QUERY
from pipefy_sdk.queries.portal_queries import GET_PORTAL_QUERY, LIST_PORTALS_QUERY
from pipefy_sdk.services.internal_api_client import InternalApiClient
from pipefy_sdk.settings import PipefySettings
from pipefy_sdk.utils.organization_identifiers import looks_like_uuid


def _with_uuid_alias(record: dict[str, Any]) -> dict[str, Any]:
    """Expose GraphQL ``id`` as ``uuid`` in portal payloads."""
    if "id" in record and "uuid" not in record:
        return {**record, "uuid": record["id"]}
    return record


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
    """GraphQL operations for Pipefy portals across multiple endpoints."""

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

    async def _resolve_organization_identifier_for_interfaces(
        self,
        organization_identifier: str,
    ) -> str:
        """Return org UUID for Interfaces GraphQL, resolving numeric ids when needed.

        Interfaces expects ``org_uuid`` / ``orgUuid``; discovery tools often expose numeric ids.

        Args:
            organization_identifier: Organization UUID or numeric organization id (string).

        Returns:
            Organization UUID for Interfaces GraphQL variables.

        Raises:
            ValueError: When the identifier is empty, invalid, or resolution yields no uuid.
        """
        trimmed = organization_identifier.strip()
        if not trimmed:
            raise ValueError("organization identifier must be non-empty")
        if looks_like_uuid(trimmed):
            return trimmed
        if trimmed.isdigit():
            result = await self._graphql_client.execute_query(
                RESOLVE_ORGANIZATION_UUID_QUERY,
                {"id": str(trimmed)},
            )
            org = result.get("organization")
            uuid_value = org.get("uuid") if isinstance(org, dict) else None
            if not uuid_value:
                raise ValueError(
                    f"Organization not found or has no uuid for id: {trimmed}"
                )
            return str(uuid_value)
        raise ValueError(
            f"organization identifier must be a UUID or numeric id, got: {trimmed!r}"
        )

    async def list_portals(
        self,
        org_uuid: str,
        search_term: str | None = None,
    ) -> list[dict[str, Any]]:
        """List portals for an organization via the Interfaces schema.

        Args:
            org_uuid: Organization UUID, or numeric organization id (string).
            search_term: Optional name filter forwarded as ``searchTerm``.
        """
        resolved_org_uuid = await self._resolve_organization_identifier_for_interfaces(
            org_uuid
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

    async def get_portal(self, uuid: str) -> dict[str, Any]:
        """Fetch a portal by UUID including pages, elements, and sub-portals.

        Args:
            uuid: Portal interface UUID.

        Raises:
            ValueError: When ``portalInterface`` resolves to null.
        """
        data = await self.execute_interfaces_query(GET_PORTAL_QUERY, {"uuid": uuid})
        portal = data.get("portalInterface")
        if portal is None:
            msg = f"Portal '{uuid}' was not found."
            raise ValueError(msg)
        return _normalize_portal_detail(portal)
