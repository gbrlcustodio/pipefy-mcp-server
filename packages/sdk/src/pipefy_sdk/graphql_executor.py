from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, NoReturn, Protocol

from gql import Client
from gql.graphql_request import GraphQLRequest
from gql.transport.exceptions import TransportQueryError
from gql.transport.httpx import HTTPXAsyncTransport
from graphql import DocumentNode, GraphQLSchema
from httpx import Auth, Timeout


@dataclass(frozen=True)
class PartialQueryResult:
    """A GraphQL response that carries ``data`` and per-node ``errors`` together.

    The executor's own value type for the partial-tolerant path, so services
    and their tests never touch gql or graphql-core objects. ``errors`` holds
    the raw GraphQL error dicts from the response body (``message`` plus an
    ``extensions`` mapping); ``data`` holds the partial payload. A response with
    no data at all is a failure and raises, so ``data`` is always a dict here.
    """

    data: dict[str, Any]
    errors: list[dict[str, Any]]


class GraphQLExecutor(Protocol):
    """The GraphQL execution seam services depend on.

    Narrow by design: it exposes only the operations services need and leaks
    nothing about the httpx/gql transport. Services receive an implementation
    through their constructor and call ``execute_query``, or
    ``execute_query_allow_partial`` when a response can mix ``data`` with
    per-node ``errors``; tests inject a fake.
    ``query`` is a parsed ``DocumentNode``: callers build one with ``gql()`` (the
    raw ``execute_graphql`` passthrough parses its string before reaching here).
    """

    async def execute_query(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> dict: ...

    async def execute_query_allow_partial(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> PartialQueryResult: ...


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
        *,
        url: str,
        auth: Auth,
        cache_schema: bool = False,
        headers: dict[str, str] | None = None,
        on_graphql_error: Callable[[list[dict]], str] | None = None,
    ) -> None:
        # Fully resolved endpoint URL; the adapter does no settings resolution itself.
        self._graphql_url = url
        self._auth = auth
        self._cache_schema = cache_schema
        self._headers = headers
        # When set, ``TransportQueryError`` is converted to ``ValueError`` using the
        # formatter's output. Used by the Internal API executor to surface its
        # ``[code=…] [correlation_id=…]`` envelope; ``None`` leaves gql exceptions
        # untouched (the public executor's behaviour).
        self._on_graphql_error = on_graphql_error
        # Caches the introspected schema so it is fetched once, not per Client.
        self._fetched_gql_schema: GraphQLSchema | None = None
        self._fetched_gql_schema_lock = asyncio.Lock()

    async def _execute_request(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> dict:
        """Run a GraphQL request on a fresh transport, honoring schema caching.

        A fresh HTTPXAsyncTransport is created per call so concurrent invocations
        each get their own isolated connection state.
        By default the gql client does not fetch the remote schema (no introspection
        per request). When ``cache_schema`` is True the schema is fetched once per
        executor instance, cached, and reused for local validation.

        Returns the ``data`` dict and raises ``TransportQueryError`` if the response
        carries GraphQL ``errors`` (gql raises even when partial ``data`` is present).
        The partial ``data`` and the ``errors`` are both available on the exception.
        """
        transport = HTTPXAsyncTransport(
            url=self._graphql_url,
            auth=self._auth,
            timeout=Timeout(timeout=self.GRAPHQL_REQUEST_TIMEOUT_SECONDS),
            verify=True,
            headers=self._headers,
        )
        request = _graphql_request_with_variables(query, variables)
        if self._cache_schema:
            if self._fetched_gql_schema is None:
                async with self._fetched_gql_schema_lock:
                    if self._fetched_gql_schema is None:
                        client = Client(
                            transport=transport,
                            fetch_schema_from_transport=True,
                        )
                        async with client as session:
                            result = await session.execute(request)
                        if client.schema is not None:
                            self._fetched_gql_schema = client.schema
                        return result
            reuse_client = Client(
                transport=transport,
                schema=self._fetched_gql_schema,
                fetch_schema_from_transport=False,
            )
            async with reuse_client as session:
                return await session.execute(request)

        async with Client(
            transport=transport, fetch_schema_from_transport=False
        ) as session:
            return await session.execute(request)

    def _reraise_graphql_error(self, exc: TransportQueryError) -> NoReturn:
        """Reraise a gql error as the executor's error type.

        With ``on_graphql_error`` set (the Internal API executor) the gql exception
        is converted to ``ValueError`` carrying the formatter's ``[code=…]`` envelope;
        otherwise the original ``TransportQueryError`` propagates unchanged.
        """
        if self._on_graphql_error is None:
            raise exc
        raise ValueError(self._on_graphql_error(exc.errors or [])) from exc

    async def execute_query(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> dict:
        """Execute a GraphQL query/mutation with variables.

        All-or-nothing semantics: gql raises ``TransportQueryError`` if the response
        carries any GraphQL ``errors`` (the partial ``data`` is discarded). For
        responses that intentionally mix data and per-node errors, use
        :meth:`execute_query_allow_partial` instead.
        """
        try:
            return await self._execute_request(query, variables)
        except TransportQueryError as exc:
            self._reraise_graphql_error(exc)

    async def execute_query_allow_partial(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> PartialQueryResult:
        """Execute a query preserving partial ``data`` alongside GraphQL ``errors``.

        Pipefy can return ``data`` for the nodes a token may access AND per-node
        ``errors`` (e.g. ``PERMISSION_DENIED`` carrying ``automation_id`` in
        ``extensions``) in a single response. gql raises ``TransportQueryError`` on
        any ``errors`` even in this mode, but attaches the partial ``data`` and the
        ``errors`` to the exception, so this rebuilds them into a
        :class:`PartialQueryResult`. A response with no ``data`` at all is a real
        failure and reraises like :meth:`execute_query`; transport-level failures
        always raise.
        """
        try:
            data = await self._execute_request(query, variables)
        except TransportQueryError as exc:
            if exc.data is None:
                self._reraise_graphql_error(exc)
            return PartialQueryResult(data=exc.data, errors=list(exc.errors or []))
        return PartialQueryResult(data=data, errors=[])
