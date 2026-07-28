"""GraphQL operations for organization service accounts (create, delete).

Service accounts are org-level OAuth2 identities. ``create`` returns the client
secret and token endpoint once — callers must persist them; there is no read-back
query. This service returns the raw payload untouched; never log the result.
"""

from __future__ import annotations

from typing import Any

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.queries.service_account_queries import (
    CREATE_SERVICE_ACCOUNT_MUTATION,
    DELETE_SERVICE_ACCOUNT_MUTATION,
)


class ServiceAccountService:
    """Create and delete organization service accounts."""

    def __init__(self, *, executor: GraphQLExecutor) -> None:
        self._executor = executor

    async def create_service_account(
        self,
        *,
        organization_uuid: str,
        name: str,
        role: str,
        description: str | None = None,
        expiration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a service account on an organization.

        Args:
            organization_uuid: The organization UUID.
            name: Service account name (backend caps at 20 characters).
            role: Organization role (e.g. 'normal', 'admin').
            description: Optional description.
            expiration: Optional token expiration ``{"unit": ..., "value": ...}``
                where unit is one of seconds/minutes/hours/days.
        """
        payload: dict[str, Any] = {
            "organizationUuid": str(organization_uuid),
            "name": name,
            "role": role,
        }
        if description is not None:
            payload["description"] = description
        if expiration is not None:
            payload["expirationTime"] = expiration
        return await self._executor.execute_query(
            CREATE_SERVICE_ACCOUNT_MUTATION, {"input": payload}
        )

    async def delete_service_account(
        self,
        *,
        organization_uuid: str,
        service_account_uuid: str,
    ) -> dict[str, Any]:
        """Delete a service account from an organization.

        Args:
            organization_uuid: The organization UUID.
            service_account_uuid: The service account UUID.
        """
        return await self._executor.execute_query(
            DELETE_SERVICE_ACCOUNT_MUTATION,
            {
                "input": {
                    "organizationUuid": str(organization_uuid),
                    "serviceAccountUuid": str(service_account_uuid),
                }
            },
        )
