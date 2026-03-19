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
    """MCP tools for GraphQL schema introspection and raw execution."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        """Register introspection-related tools on the MCP server."""

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def introspect_type(type_name: str) -> dict:
            """Inspect a Pipefy GraphQL type: fields, inputFields, or enumValues.

            Use before building raw queries to learn argument and return shapes.

            Args:
                type_name: Schema type name exactly as defined (e.g. Card, Mutation).
            """
            result = await client.introspect_type(type_name)
            err = result.get("error")
            if isinstance(err, str) and err:
                return build_error_payload(err)
            return build_success_payload(result)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def introspect_mutation(mutation_name: str) -> dict:
            """Inspect a root GraphQL mutation: arguments and return type.

            Use before execute_graphql to learn required inputs and payload shape.

            Args:
                mutation_name: Mutation field name on the Mutation type (e.g. createCard).
            """
            result = await client.introspect_mutation(mutation_name)
            err = result.get("error")
            if isinstance(err, str) and err:
                return build_error_payload(err)
            return build_success_payload(result)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def search_schema(keyword: str) -> dict:
            """Search GraphQL schema types by keyword in name or description.

            Case-insensitive; introspection types (names starting with __) are excluded server-side.

            Args:
                keyword: Substring to find relevant types (e.g. pipe, card, automation).
            """
            result = await client.search_schema(keyword)
            err = result.get("error")
            if isinstance(err, str) and err:
                return build_error_payload(err)
            return build_success_payload(result)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def execute_graphql(
            query: str,
            variables: dict[str, Any] | None = None,
        ) -> dict:
            """Run arbitrary GraphQL against Pipefy (queries or mutations).

            Prefer dedicated tools when available. Use this as a fallback when no specific
            tool exists. Always introspect the mutation's input shape before executing.

            Args:
                query: Full GraphQL document (query or mutation).
                variables: Optional variable map for the operation.
            """
            result = await client.execute_graphql(query, variables)
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
            return build_success_payload(result)
