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
class GraphQLResult:
    """GraphQL ``data`` plus the raw per-node error dicts from one response.

    A GraphQL response can carry readable ``data`` and per-node ``errors`` at the
    same time, so the primitive hands both back together. Owned by the executor
    so services and their tests never touch gql objects. ``data`` is always a
    dict; a fully null response yields an empty one.
    """

    data: dict[str, Any]
    errors: list[dict[str, Any]]


class GraphQLExecutor(Protocol):
    """The GraphQL execution seam services depend on.

    Narrow by design: it exposes only what services need. Its return types are
    owned (:class:`GraphQLResult` and a plain ``dict``); the one gql type it
    surfaces is the ``TransportQueryError`` a formatter-less :meth:`execute_query`
    raises. Services receive an implementation through their constructor and call
    one of two methods; tests inject a fake.

    :meth:`execute` is the primitive: it performs the request and returns
    ``data`` and ``errors`` together, deciding nothing about what the errors
    mean. :meth:`execute_query` is the raise-on-error convenience layered over
    it, for the callers that want data or an exception and nothing in between. A
    service that needs partial-success handling calls :meth:`execute` and hands
    the errors to its own classifier.

    ``query`` is a parsed ``DocumentNode``: callers build one with ``gql()`` (the
    raw ``execute_graphql`` passthrough parses its string before reaching here).
    """

    async def execute(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> GraphQLResult: ...

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
        # How execute_query surfaces GraphQL errors. When set, it raises a
        # ValueError carrying the formatter's output; used by the Internal API
        # endpoint for its [code=…] [correlation_id=…] envelope. When None it
        # re-raises the gql TransportQueryError shape (the public endpoint's
        # behaviour). The primitive execute never applies it.
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

    async def execute(
        self, query: DocumentNode, variables: dict[str, Any], *, auth: Auth
    ) -> GraphQLResult:
        """Execute a query and return its ``data`` and raw ``errors`` together.

        The primitive: it performs the effect and decides nothing about what the
        errors mean. gql raises on any ``errors`` but attaches the partial ``data``
        and the raw error dicts to the exception; this rebuilds them into a
        :class:`GraphQLResult`. A fully null response yields ``data={}`` with its
        errors preserved. Genuine transport/network failures (timeouts, non-2xx)
        still raise.
        """
        try:
            data = await self._execute_request(query, variables, auth=auth)
        except TransportQueryError as exc:
            return GraphQLResult(data=exc.data or {}, errors=list(exc.errors or []))
        return GraphQLResult(data=data, errors=[])

    async def execute_query(
        self, query: DocumentNode, variables: dict[str, Any], *, auth: Auth
    ) -> dict:
        """Run :meth:`execute` and return ``data``, raising if the response held errors.

        The raise-on-error convenience the query/mutation tools use: they want
        ``data`` or an exception, not partial success. On GraphQL ``errors`` the
        error formatter decides the exception (see :meth:`_raise_for_errors`).
        """
        result = await self.execute(query, variables, auth=auth)
        if result.errors:
            self._raise_for_errors(result.errors, data=result.data)
        return result.data

    def _raise_for_errors(
        self, errors: list[dict[str, Any]], *, data: dict[str, Any]
    ) -> NoReturn:
        if self._on_graphql_error is not None:
            raise ValueError(self._on_graphql_error(errors))
        # Without a formatter, re-raise gql's error shape so callers that read the
        # structured ``errors`` list off the exception keep working unchanged.
        raise TransportQueryError(str(errors[0]), errors=errors, data=data)


@dataclass(frozen=True)
class AuthenticatedExecutor:
    """A :class:`GraphQLEndpoint` bound to one identity's ``auth``.

    The cheap per-session executor: it implements :class:`GraphQLExecutor` by
    delegating to the shared endpoint with its own ``auth``. Cheap to build one
    per request; the endpoint (and its schema cache) is reused across all of them.
    """

    endpoint: GraphQLEndpoint
    auth: Auth

    async def execute(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> GraphQLResult:
        return await self.endpoint.execute(query, variables, auth=self.auth)

    async def execute_query(
        self, query: DocumentNode, variables: dict[str, Any]
    ) -> dict:
        return await self.endpoint.execute_query(query, variables, auth=self.auth)
