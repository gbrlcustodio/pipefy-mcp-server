from __future__ import annotations

from typing import Any, ClassVar

from gql import Client
from gql.transport.httpx import HTTPXAsyncTransport
from httpx import Timeout
from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.settings import PipefySettings


class BasePipefyClient:
    """Base infrastructure for Pipefy GraphQL operations.

    Creates a fresh transport per execute_query() call so parallel requests
    never share mutable transport state (avoids TransportAlreadyConnected).
    The OAuth2 auth instance is shared across calls to reuse the token cache.
    """

    GRAPHQL_REQUEST_TIMEOUT_SECONDS: ClassVar[int] = 30

    def __init__(self, settings: PipefySettings) -> None:
        if settings is None:
            raise ValueError("Settings must be provided to create a GraphQL client.")
        if settings.graphql_url is None:
            raise ValueError("GraphQL URL must be provided in settings.")
        if settings.oauth_url is None:
            raise ValueError("OAuth URL must be provided in settings.")
        if settings.oauth_client is None:
            raise ValueError("OAuth client ID must be provided in settings.")
        if settings.oauth_secret is None:
            raise ValueError("OAuth client secret must be provided in settings.")

        self.settings = settings
        self._auth = OAuth2ClientCredentials(
            token_url=settings.oauth_url,
            client_id=settings.oauth_client,
            client_secret=settings.oauth_secret,
        )

    async def execute_query(self, query: Any, variables: dict[str, Any]) -> dict:
        """Execute a GraphQL query/mutation with variables.

        A fresh HTTPXAsyncTransport is created per call so concurrent invocations
        each get their own isolated connection state.
        """
        transport = HTTPXAsyncTransport(
            url=self.settings.graphql_url,
            auth=self._auth,
            timeout=Timeout(timeout=self.GRAPHQL_REQUEST_TIMEOUT_SECONDS),
        )
        async with Client(transport=transport, fetch_schema_from_transport=False) as session:
            return await session.execute(query, variable_values=variables)
