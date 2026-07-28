"""Service for fetching Pipefy organization data."""

from __future__ import annotations

from typing import Any

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.queries.organization_queries import (
    GET_ORGANIZATION_QUERY,
    LIST_ORGANIZATIONS_QUERY,
)


class OrganizationService:
    """GraphQL operations for Pipefy organizations."""

    def __init__(self, *, executor: GraphQLExecutor) -> None:
        self._executor = executor

    async def get_organization(self, organization_id: str) -> dict[str, Any]:
        """Fetch organization details by ID.

        Args:
            organization_id: Numeric organization ID.
        """
        data = await self._executor.execute_query(
            GET_ORGANIZATION_QUERY, {"id": str(organization_id)}
        )
        org = data.get("organization")
        if org is None:
            msg = f"Organization '{organization_id}' was not found."
            raise ValueError(msg)
        return org

    async def list_organizations(self) -> list[dict[str, Any]]:
        """List the organizations the caller can access.

        Needs no id: the API scopes the result to the caller's own access. An
        empty list is a valid answer (the caller belongs to no organization), so
        unlike ``get_organization`` this does not raise on an empty result.
        """
        data = await self._executor.execute_query(LIST_ORGANIZATIONS_QUERY, {})
        return data.get("organizations") or []
