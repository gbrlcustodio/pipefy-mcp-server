"""Service for Pipefy portal operations (Interfaces + internal_api routing)."""

from __future__ import annotations

from typing import Any

from httpx import Auth

from pipefy_sdk.base_client import BasePipefyClient, unwrap_relay_connection_nodes
from pipefy_sdk.queries.portal_queries import GET_PORTAL_QUERY, LIST_PORTALS_QUERY
from pipefy_sdk.services.internal_api_client import InternalApiClient
from pipefy_sdk.settings import PipefySettings


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
        org_uuid: str,
        search_term: str | None = None,
    ) -> list[dict[str, Any]]:
        """List portals for an organization via the Interfaces schema.

        Args:
            org_uuid: Organization UUID.
            search_term: Optional name filter forwarded as ``searchTerm``.
        """
        variables: dict[str, Any] = {
            "org_uuid": org_uuid,
            "filterBySubType": "portal",
        }
        if search_term is not None:
            variables["searchTerm"] = search_term
        data = await self.execute_interfaces_query(LIST_PORTALS_QUERY, variables)
        return unwrap_relay_connection_nodes(data.get("interfaces"))

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
        return portal
