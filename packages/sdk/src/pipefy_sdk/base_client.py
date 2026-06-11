from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, ClassVar

from gql import Client
from gql.transport.exceptions import TransportQueryError
from gql.transport.httpx import HTTPXAsyncTransport
from graphql import GraphQLSchema
from httpx import Auth, Timeout

from pipefy_sdk.settings import PipefySettings


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
    The ``auth`` instance is shared across calls to reuse the token cache.
    Pass the same instance to multiple services (e.g. from PipefyClient) so
    only one token cache exists for the whole client.
    """

    GRAPHQL_REQUEST_TIMEOUT_SECONDS: ClassVar[int] = 30

    def __init__(
        self,
        settings: PipefySettings,
        *,
        auth: Auth,
        url_override: str | None = None,
        on_graphql_error: Callable[[list[dict]], str] | None = None,
    ) -> None:
        # ``url_override`` lets callers point this client at a sibling endpoint
        # (e.g. ``PortalService`` aims its interfaces client at
        # ``settings.interfaces_graphql_url``) without mutating the shared
        # settings object. Defaults to ``settings.graphql_url``.
        self.settings = settings
        self._auth = auth
        self._graphql_url = url_override or settings.graphql_url
        # When set, ``TransportQueryError`` is converted to ``ValueError`` using the
        # formatter's output. Used by ``InternalApiClient`` to surface its
        # ``[code=…] [correlation_id=…]`` envelope; ``None`` leaves gql exceptions
        # untouched (PipefyClient's behaviour).
        self._on_graphql_error = on_graphql_error
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
            url=self._graphql_url,
            auth=self._auth,
            timeout=Timeout(timeout=self.GRAPHQL_REQUEST_TIMEOUT_SECONDS),
            verify=True,
        )
        try:
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
        except TransportQueryError as exc:
            if self._on_graphql_error is None:
                raise
            raise ValueError(self._on_graphql_error(exc.errors or [])) from exc
