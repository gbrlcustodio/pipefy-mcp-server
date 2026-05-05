"""MCP tools for GraphQL schema introspection and raw ``execute_graphql``."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.introspection_tool_helpers import (
    build_error_payload,
    build_success_payload,
)


class IntrospectionTools:
    """Registers MCP tools for schema introspection and ``execute_graphql``."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        """Register introspection-related tools on the MCP server."""

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def introspect_type(
            type_name: str,
            max_depth: int = 1,
            include_parsed: bool = False,
        ) -> dict:
            """Inspect a Pipefy GraphQL type: fields, inputFields, or enumValues.

            Use before building raw queries to learn argument and return shapes.
            Returns ``result`` (pretty-printed JSON string).  Set ``include_parsed=True``
            to also get a ``data`` dict for programmatic access.

            Args:
                type_name: Schema type name exactly as defined (e.g. Card, Mutation).
                max_depth: Levels of sub-types to resolve (1 = no recursion, 2+ = inline referenced types).
                include_parsed: When True, include ``data`` dict alongside ``result``.
            """
            try:
                result = await client.introspect_type(type_name, max_depth=max_depth)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))
            err = result.get("error")
            if isinstance(err, str) and err:
                return build_error_payload(err)
            return build_success_payload(result, include_parsed=include_parsed)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def introspect_mutation(
            mutation_name: str,
            max_depth: int = 1,
            include_parsed: bool = False,
        ) -> dict:
            """Inspect a root GraphQL mutation: arguments and return type.

            Use before execute_graphql to learn required inputs and payload shape.
            Returns ``result`` (pretty-printed JSON string).  Set ``include_parsed=True``
            to also get a ``data`` dict for programmatic access.

            Args:
                mutation_name: Mutation field name on the Mutation type (e.g. createCard).
                max_depth: Levels of sub-types to resolve (1 = no recursion, 2+ = inline referenced types).
                include_parsed: When True, include ``data`` dict alongside ``result``.
            """
            try:
                result = await client.introspect_mutation(
                    mutation_name, max_depth=max_depth
                )
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))
            err = result.get("error")
            if isinstance(err, str) and err:
                return build_error_payload(err)
            return build_success_payload(result, include_parsed=include_parsed)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def introspect_query(
            query_name: str,
            max_depth: int = 1,
            include_parsed: bool = False,
        ) -> dict:
            """Inspect a root GraphQL query: arguments and return type.

            Use before execute_graphql to learn required inputs and payload shape.
            Returns ``result`` (pretty-printed JSON string).  Set ``include_parsed=True``
            to also get a ``data`` dict for programmatic access.

            Args:
                query_name: Query field name on the Query type (e.g. pipe, organization).
                max_depth: Levels of sub-types to resolve (1 = no recursion, 2+ = inline referenced types).
                include_parsed: When True, include ``data`` dict alongside ``result``.
            """
            try:
                result = await client.introspect_query(query_name, max_depth=max_depth)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))
            err = result.get("error")
            if isinstance(err, str) and err:
                return build_error_payload(err)
            return build_success_payload(result, include_parsed=include_parsed)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def search_schema(
            keyword: str,
            kind: str | None = None,
            include_parsed: bool = False,
        ) -> dict:
            """Search GraphQL schema types by keyword in name or description.

            Case-insensitive; introspection types (names starting with __) are excluded server-side.
            Returns ``result`` (pretty-printed JSON string).  Set ``include_parsed=True``
            to also get a ``data`` dict for programmatic access.

            Args:
                keyword: Substring to find relevant types (e.g. pipe, card, automation).
                kind: Optional filter by GraphQL type kind (e.g. OBJECT, INPUT_OBJECT, ENUM, SCALAR).
                include_parsed: When True, include ``data`` dict alongside ``result``.
            """
            try:
                result = await client.search_schema(keyword, kind=kind)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))
            err = result.get("error")
            if isinstance(err, str) and err:
                return build_error_payload(err)
            return build_success_payload(result, include_parsed=include_parsed)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def execute_graphql(
            query: str,
            variables: dict[str, Any] | None = None,
            include_parsed: bool = False,
        ) -> dict:
            """Run arbitrary GraphQL against Pipefy (queries or mutations).

            Prefer dedicated tools when available. Use this as a fallback when no specific
            tool exists. Always introspect the mutation's input shape before executing.
            Returns ``result`` (pretty-printed JSON string).  Set ``include_parsed=True``
            to also get a ``data`` dict for programmatic access.

            Args:
                query: Full GraphQL document (query or mutation).
                variables: Optional variable map for the operation.
                include_parsed: When True, include ``data`` dict alongside ``result``.
            """
            try:
                result = await client.execute_graphql(query, variables)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))
            gql_errors = result.get("errors")
            if isinstance(gql_errors, list) and gql_errors:
                messages: list[str] = []
                for item in gql_errors:
                    if isinstance(item, dict):
                        msg = item.get("message")
                        if isinstance(msg, str) and msg:
                            messages.append(msg)
                text = "; ".join(messages) if messages else "GraphQL returned errors."
                return build_error_payload(text)
            err = result.get("error")
            if isinstance(err, str) and err:
                return build_error_payload(err)
            return build_success_payload(result, include_parsed=include_parsed)
