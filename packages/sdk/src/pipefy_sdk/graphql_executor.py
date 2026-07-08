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
    """GraphQL ``data`` plus the raw per-node error dicts from one response.

    Owned by the executor so services and their tests never touch gql objects.
    ``data`` is always a dict; a fully null response yields an empty one.
    """

    data: dict[str, Any]
    errors: list[dict[str, Any]]


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


class PartialGraphQLExecutor(GraphQLExecutor, Protocol):
    """:class:`GraphQLExecutor` plus a partial-tolerant execute path.

    For services whose queries mix ``data`` with per-node ``errors`` in one
    response; everything else depends on the narrower protocol.
    """

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


class GraphQLEndpoint:
    """The shared, auth-less half of a Pipefy GraphQL connection.

    Holds everything about one endpoint that does not depend on the caller's
    identity: its URL, telemetry headers, error formatting, and the introspected
    schema cache. Built once and shared across identities; the execute methods take
    the ``auth`` per call so the same endpoint (and its one schema cache) serves
    every caller. A fresh transport is opened per call so concurrent requests never
    share mutable transport state (avoids ``TransportAlreadyConnected``).
    """

    GRAPHQL_REQUEST_TIMEOUT_SECONDS: ClassVar[int] = 30

    def __init__(
        self,
        *,
        url: str,
        cache_schema: bool = False,
        headers: dict[str, str] | None = None,
        on_graphql_error: Callable[[list[dict]], str] | None = None,
    ) -> None:
        # Fully resolved endpoint URL; the endpoint does no settings resolution itself.
        self._graphql_url = url
        self._cache_schema = cache_schema
        self._headers = headers
        # When set, ``TransportQueryError`` is converted to ``ValueError`` using the
        # formatter's output. Used by the Internal API endpoint to surface its
        # ``[code=…] [correlation_id=…]`` envelope; ``None`` leaves gql exceptions
        # untouched (the public endpoint's behaviour).
        self._on_graphql_error = on_graphql_error
        # Caches the introspected schema so it is fetched once, not per Client.
        self._fetched_gql_schema: GraphQLSchema | None = None
        self._fetched_gql_schema_lock = asyncio.Lock()

    async def _execute_request(
        self, query: DocumentNode, variables: dict[str, Any], *, auth: Auth
    ) -> dict:
        """Run a GraphQL request on a fresh transport, honoring schema caching.

        A fresh HTTPXAsyncTransport is created per call so concurrent invocations
        each get their own isolated connection state. ``auth`` is supplied by the
        caller (the per-session executor) rather than captured at construction, so
        one endpoint serves every identity.
        By default the gql client does not fetch the remote schema (no introspection
        per request). When ``cache_schema`` is True the schema is fetched once per
        endpoint instance, cached, and reused for local validation.

        Any GraphQL ``errors`` raise ``TransportQueryError`` (even alongside partial
        ``data``); the exception carries both ``data`` and ``errors``.
        """
        transport = HTTPXAsyncTransport(
            url=self._graphql_url,
            auth=auth,
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
        if self._on_graphql_error is None:
            raise exc
        raise ValueError(self._on_graphql_error(exc.errors or [])) from exc

    async def execute(
        self, query: DocumentNode, variables: dict[str, Any], *, auth: Auth
    ) -> dict:
        """Execute a GraphQL query/mutation with variables under ``auth``.

        All-or-nothing: any GraphQL ``errors`` raise and partial ``data`` is
        discarded; for responses that mix both, use :meth:`execute_allow_partial`.
        """
        try:
            return await self._execute_request(query, variables, auth=auth)
        except TransportQueryError as exc:
            self._reraise_graphql_error(exc)

    async def execute_allow_partial(
        self, query: DocumentNode, variables: dict[str, Any], *, auth: Auth
    ) -> PartialQueryResult:
        """Execute a query preserving partial ``data`` alongside GraphQL ``errors``.

        gql raises on any ``errors`` but attaches the partial ``data`` and the raw
        error dicts to the exception; this rebuilds them into a
        :class:`PartialQueryResult`. A fully null response yields ``data={}`` with
        its errors preserved: whether an empty result is a failure is the caller's
        decision, not the transport's.
        """
        try:
            data = await self._execute_request(query, variables, auth=auth)
        except TransportQueryError as exc:
            return PartialQueryResult(
                data=exc.data or {}, errors=list(exc.errors or [])
            )
        return PartialQueryResult(data=data, errors=[])


@dataclass(frozen=True)
class AuthenticatedExecutor:
    """A :class:`GraphQLEndpoint` bound to one identity's ``auth``.

    The cheap per-session executor: it implements :class:`PartialGraphQLExecutor`
    by delegating to the shared endpoint with its own ``auth``. Cheap to build one
    per request; the endpoint (and its schema cache) is reused across all of them.
    """

    endpoint: GraphQLEndpoint
    auth: Auth

    async def execute_query(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> dict:
        return await self.endpoint.execute(query, variables, auth=self.auth)

    async def execute_query_allow_partial(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> PartialQueryResult:
        return await self.endpoint.execute_allow_partial(
            query, variables, auth=self.auth
        )
