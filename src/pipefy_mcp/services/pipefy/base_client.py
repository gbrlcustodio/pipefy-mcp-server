from __future__ import annotations

from typing import Any

from gql import Client
from gql.transport.httpx import HTTPXAsyncTransport
from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.settings import settings


class BasePipefyClient:
    """Base infrastructure for Pipefy GraphQL operations.

    This class centralizes GraphQL client creation so services can reuse a single
    underlying `gql.Client` instance via constructor injection.
    """

    def __init__(
        self, schema: str | None = None, client: Client | None = None
    ) -> None:
        """Create a base client.

        Args:
            schema: Optional schema string to pass to `gql.Client`.
            client: Optional pre-built `gql.Client` to reuse (preferred for shared wiring).
        """

        self.client: Client = client or self._create_client(schema)

    def _create_client(self, schema: str | None) -> Client:
        """Create and configure a `gql.Client` using project settings.

        Note: This preserves the current behavior from `PipefyClient._create_client`.
        """

        transport = HTTPXAsyncTransport(
            url=settings.pipefy_graphql_url,
            auth=OAuth2ClientCredentials(
                token_url=settings.pipefy_oauth_url,
                client_id=settings.pipefy_oauth_client,
                client_secret=settings.pipefy_oauth_secret,
            ),
        )

        kwargs = {"schema": schema} if schema else {"fetch_schema_from_transport": True}
        return Client(transport=transport, **kwargs)

    async def execute_query(self, query: Any, variables: dict[str, Any]) -> dict:
        """Execute a GraphQL query/mutation with variables.

        This method standardizes session usage and preserves current behavior by
        passing `variable_values` through without transformation.
        """

        async with self.client as session:
            return await session.execute(query, variable_values=variables)
