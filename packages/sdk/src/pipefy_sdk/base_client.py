from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from gql import Client
from gql.transport.httpx import HTTPXAsyncTransport
from graphql import GraphQLSchema
from httpx import Auth, Request, Timeout
from httpx_auth import OAuth2ClientCredentials

from pipefy_sdk.settings import PipefySettings


class StaticBearerAuth(Auth):
    """Attach a fixed ``Authorization: Bearer …`` header (CLI ``--token``, tests)."""

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: Request):
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


def unwrap_relay_connection_nodes(connection: Any) -> list[dict[str, Any]]:
    """Collect ``node`` dicts from a Relay-style GraphQL connection (edges → node)."""
    if not isinstance(connection, dict):
        return []
    edges = connection.get("edges")
    if not isinstance(edges, list):
        return []
    nodes: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        node = edge.get("node")
        if isinstance(node, dict):
            nodes.append(node)
    return nodes


class BasePipefyClient:
    """Base infrastructure for Pipefy GraphQL operations.

    Creates a fresh transport per execute_query() call so parallel requests
    never share mutable transport state (avoids TransportAlreadyConnected).
    The OAuth2 auth instance is shared across calls to reuse the token cache.
    Pass a pre-built auth instance to share it across multiple service instances
    (e.g. from PipefyClient) so only one token cache exists for the whole client.
    """

    GRAPHQL_REQUEST_TIMEOUT_SECONDS: ClassVar[int] = 30

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | Auth | None = None,
    ) -> None:
        if settings.graphql_url is None:
            raise ValueError("GraphQL URL must be provided in settings.")

        self.settings = settings

        if auth is not None and not isinstance(auth, OAuth2ClientCredentials):
            self._auth = auth
            self._fetched_gql_schema = None
            self._fetched_gql_schema_lock = asyncio.Lock()
            return

        if settings.service_account_url is None:
            raise ValueError("Service-account URL must be provided in settings.")
        if settings.service_account_client_id is None:
            raise ValueError("Service-account client ID must be provided in settings.")
        if settings.service_account_client_secret is None:
            raise ValueError(
                "Service-account client secret must be provided in settings."
            )

        self._auth = auth or OAuth2ClientCredentials(
            token_url=settings.service_account_url,
            client_id=settings.service_account_client_id,
            client_secret=settings.service_account_client_secret,
        )
        # Populated when gql_reuse_fetched_graphql_schema is True; avoids repeating
        # introspection on every new Client (see Cons5 code review).
        self._fetched_gql_schema: GraphQLSchema | None = None
        self._fetched_gql_schema_lock = asyncio.Lock()

    async def execute_query(self, query: Any, variables: dict[str, Any]) -> dict:
        """Execute a GraphQL query/mutation with variables.

        A fresh HTTPXAsyncTransport is created per call so concurrent invocations
        each get their own isolated connection state.
        By default the gql client does not fetch the remote schema (no introspection
        per request). Optional ``pipefy.gql_reuse_fetched_graphql_schema`` fetches
        once per client instance, caches the schema, and reuses it for local validation.
        """
        transport = HTTPXAsyncTransport(
            url=self.settings.graphql_url,
            auth=self._auth,
            timeout=Timeout(timeout=self.GRAPHQL_REQUEST_TIMEOUT_SECONDS),
        )
        if self.settings.gql_reuse_fetched_graphql_schema:
            if self._fetched_gql_schema is None:
                async with self._fetched_gql_schema_lock:
                    if self._fetched_gql_schema is None:
                        client = Client(
                            transport=transport,
                            fetch_schema_from_transport=True,
                        )
                        async with client as session:
                            result = await session.execute(
                                query, variable_values=variables
                            )
                        if client.schema is not None:
                            self._fetched_gql_schema = client.schema
                        return result
            reuse_client = Client(
                transport=transport,
                schema=self._fetched_gql_schema,
                fetch_schema_from_transport=False,
            )
            async with reuse_client as session:
                return await session.execute(query, variable_values=variables)

        async with Client(
            transport=transport, fetch_schema_from_transport=False
        ) as session:
            return await session.execute(query, variable_values=variables)
