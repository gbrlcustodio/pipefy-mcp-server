from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

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


def _graphql_error_message(errors: list[dict[str, Any]]) -> str:
    """Join the human-readable messages from raw GraphQL error dicts."""
    joined = "; ".join(err.get("message") or "Unknown error" for err in errors)
    return joined or "Query failed."


class PipefyGraphQLError(Exception):
    """A GraphQL response came back carrying ``errors``.

    Owned by the SDK so callers catch one error type instead of a gql transport
    exception. ``errors`` is the raw per-node error dict list (each with its own
    ``message`` and ``extensions``); consumers read codes and correlation ids off
    that structure rather than parsing the message string.
    """

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__(_graphql_error_message(errors))


def data_or_raise(result: GraphQLResult) -> dict:
    """Return ``result.data``, or raise :class:`PipefyGraphQLError` if it held errors.

    The raise-on-error decision as a pure function: it is what the query and
    mutation callers want (data or an exception, nothing in between) without the
    seam itself deciding that a response with errors is a failure. Services that
    handle partial success skip it and read ``result.errors`` directly.
    """
    if result.errors:
        raise PipefyGraphQLError(result.errors)
    return result.data


class GraphQLExecutor(Protocol):
    """The GraphQL execution seam services depend on.

    Narrow by design: it exposes only what services need and leaks nothing about
    the httpx/gql transport. :meth:`execute` returns an owned
    :class:`GraphQLResult`, and :meth:`execute_query` raises an owned
    :class:`PipefyGraphQLError`. Services receive an implementation through their
    constructor and call one of two methods; tests inject a fake.

    :meth:`execute` is the primitive: it performs the request and returns
    ``data`` and ``errors`` together, deciding nothing about what the errors
    mean. :meth:`execute_query` is the raise-on-error convenience layered over it
    (via :func:`data_or_raise`), for the callers that want data or an exception
    and nothing in between. A service that needs partial-success handling calls
    :meth:`execute` and hands the errors to its own classifier.

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
    identity: its URL, telemetry headers, and the introspected schema cache. Built
    once and shared across identities; the execute methods take the ``auth`` per
    call so the same endpoint (and its one schema cache) serves every caller. A
    fresh transport is opened per call so concurrent requests never share mutable
    transport state (avoids ``TransportAlreadyConnected``).
    """

    GRAPHQL_REQUEST_TIMEOUT_SECONDS: ClassVar[int] = 30

    def __init__(
        self,
        *,
        url: str,
        cache_schema: bool = False,
        headers: dict[str, str] | None = None,
    ) -> None:
        # Fully resolved endpoint URL; the endpoint does no settings resolution itself.
        self._graphql_url = url
        self._cache_schema = cache_schema
        self._headers = headers
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
        ``data`` or an exception, not partial success. On GraphQL ``errors`` it
        raises :class:`PipefyGraphQLError` (see :func:`data_or_raise`).
        """
        return data_or_raise(await self.execute(query, variables, auth=auth))


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
