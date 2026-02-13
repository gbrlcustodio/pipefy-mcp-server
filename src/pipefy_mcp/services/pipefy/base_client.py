from __future__ import annotations

import asyncio
from typing import Any, cast

from gql import Client
from gql.transport.httpx import HTTPXAsyncTransport
from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.settings import PipefySettings


class BasePipefyClient:
    """Base infrastructure for Pipefy GraphQL operations.

    This class centralizes GraphQL client creation so services can reuse a single
    underlying `gql.Client` instance via constructor injection.
    """

    def __init__(
        self,
        settings: PipefySettings | None = None,
        schema: str | None = None,
        client: Client | None = None,
        client_lock: asyncio.Lock | None = None,
    ) -> None:
        """Create a base client.

        Args:
            schema: Optional schema string to pass to `gql.Client`.
            client: Optional pre-built `gql.Client` to reuse (preferred for shared wiring).
            client_lock: Optional lock to serialize access to the shared client; use when
                multiple services share the same client so concurrent tool calls do not
                trigger \"Transport is already connected\".

        Raises:
            ValueError: If both schema and client are provided, as schema would be ignored.
        """
        if schema is not None and client is not None:
            raise ValueError(
                "Cannot specify both 'schema' and 'client'. "
                "When reusing an existing client, its schema is already configured."
            )

        self.settings = settings
        self.client: Client = client or self._create_client(schema)
        self._client_lock: asyncio.Lock = client_lock if client_lock is not None else asyncio.Lock()

    def _create_client(self, schema: str | None) -> Client:
        """Create and configure a `gql.Client` using project settings.

        Note: This preserves the current behavior from `PipefyClient._create_client`.
        """

        if self.settings is None:
            raise ValueError("Settings must be provided to create a GraphQL client.")

        if self.settings.graphql_url is None:
            raise ValueError("GraphQL URL must be provided in settings.")
        if self.settings.oauth_url is None:
            raise ValueError("OAuth URL must be provided in settings.")
        if self.settings.oauth_client is None:
            raise ValueError("OAuth client ID must be provided in settings.")
        if self.settings.oauth_secret is None:
            raise ValueError("OAuth client secret must be provided in settings.")

        transport = HTTPXAsyncTransport(
            url=self.settings.graphql_url,
            auth=OAuth2ClientCredentials(
                token_url=self.settings.oauth_url,
                client_id=self.settings.oauth_client,
                client_secret=self.settings.oauth_secret,
            ),
        )

        if schema:
            return Client(transport=transport, schema=schema)
        return Client(transport=transport, fetch_schema_from_transport=True)

    async def execute_query(self, query: Any, variables: dict[str, Any]) -> dict[str, Any]:
        """Execute a GraphQL query/mutation with variables.

        This method standardizes session usage and preserves current behavior by
        passing `variable_values` through without transformation. Access to the
        shared gql Client is serialized with a lock so that concurrent tool
        calls (e.g. get_pipe and get_start_form_fields in parallel) do not
        trigger \"Transport is already connected\" from the underlying transport.
        """
        async with self._client_lock:
            async with self.client as session:
                result = await session.execute(query, variable_values=variables)
                return cast(dict[str, Any], result)
