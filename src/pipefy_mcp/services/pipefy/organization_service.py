"""Service for fetching Pipefy organization data."""

from __future__ import annotations

from typing import Any

from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.organization_queries import (
    GET_ORGANIZATION_QUERY,
)
from pipefy_mcp.settings import PipefySettings


class OrganizationService(BasePipefyClient):
    """GraphQL operations for Pipefy organizations."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def get_organization(self, organization_id: str) -> dict[str, Any]:
        """Fetch organization details by ID.

        Args:
            organization_id: Numeric organization ID.
        """
        data = await self.execute_query(
            GET_ORGANIZATION_QUERY, {"id": int(organization_id)}
        )
        org = data.get("organization")
        if org is None:
            return {
                "error": f"Organization '{organization_id}' was not found.",
            }
        return org
