from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, ClassVar, Protocol

from gql import Client
from gql.graphql_request import GraphQLRequest
from gql.transport.exceptions import TransportQueryError
from gql.transport.httpx import HTTPXAsyncTransport
from graphql import DocumentNode, GraphQLSchema
from httpx import Auth, Timeout

from pipefy_sdk.settings import PipefySettings


class GraphQLExecutor(Protocol):
    """The GraphQL execution seam services depend on.

    Narrow by design: it exposes only the operation services need and leaks
    nothing about the httpx/gql transport. Services receive an implementation
    through their constructor and call ``execute_query``; tests inject a fake.
    ``query`` is a parsed ``DocumentNode``: callers build one with ``gql()`` (the
    raw ``execute_graphql`` passthrough parses its string before reaching here).
    """

    async def execute_query(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> dict: ...


def _graphql_request_with_variables(
    query: DocumentNode, variables: dict[str, Any]
) -> GraphQLRequest:
    """Bind variables on a fresh request so shared ``gql()`` constants stay immutable.

    An empty ``variables`` dict omits ``variable_values`` (``None``) on the request.
    """
    return GraphQLRequest(query, variable_values=variables if variables else None)


class HttpxGraphQLExecutor:
    """The sole httpx/gql adapter implementing :class:`GraphQLExecutor`.

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
        # ``url_override`` lets callers point this executor at a sibling endpoint
        # (e.g. the interfaces or internal_api URL derived from the same
        # ``settings``) without mutating the shared settings object. Defaults to
        # ``settings.graphql_url``.
        self.settings = settings
        self._auth = auth
        self._graphql_url = url_override or settings.graphql_url
        # When set, ``TransportQueryError`` is converted to ``ValueError`` using the
        # formatter's output. Used by the internal_api executor to surface its
        # ``[code=…] [correlation_id=…]`` envelope; ``None`` leaves gql exceptions
        # untouched (the public executor's behaviour).
        self._on_graphql_error = on_graphql_error
        # Populated when gql_reuse_fetched_graphql_schema is True; avoids repeating
        # introspection on every new Client.
        self._fetched_gql_schema: GraphQLSchema | None = None
        self._fetched_gql_schema_lock = asyncio.Lock()

    async def execute_query(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> dict:
        """Execute a GraphQL query/mutation with variables.

        A fresh HTTPXAsyncTransport is created per call so concurrent invocations
        each get their own isolated connection state.
        By default the gql client does not fetch the remote schema (no introspection
        per request). Optional ``pipefy.gql_reuse_fetched_graphql_schema`` fetches
        once per executor instance, caches the schema, and reuses it for local validation.
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
                                    _graphql_request_with_variables(query, variables)
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
                    return await session.execute(
                        _graphql_request_with_variables(query, variables)
                    )

            async with Client(
                transport=transport, fetch_schema_from_transport=False
            ) as session:
                return await session.execute(
                    _graphql_request_with_variables(query, variables)
                )
        except TransportQueryError as exc:
            if self._on_graphql_error is None:
                raise
            raise ValueError(self._on_graphql_error(exc.errors or [])) from exc
