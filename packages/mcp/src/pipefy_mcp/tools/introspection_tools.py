"""MCP tools for GraphQL schema introspection and raw ``execute_graphql``."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pipefy_sdk.graphql_document import inspect_graphql_document

from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import ensure_non_empty_error_message
from pipefy_mcp.tools.introspection_tool_helpers import (
    build_error_payload,
    build_success_payload,
)
from pipefy_mcp.tools.remote_profile import REMOTE
from pipefy_mcp.tools.tool_context import get_pipefy_client

_GRAPHQL_TOOL_REQUEST_FAILED = "GraphQL request failed."
_EXECUTE_GRAPHQL_FAILED = (
    "GraphQL request failed. If this was a write, re-read counts/ids "
    "before retrying; do not blind-retry."
)
_GRAPHQL_RETURNED_ERRORS = "GraphQL returned errors."


def _exception_error_payload(exc: BaseException, fallback: str) -> dict:
    return build_error_payload(ensure_non_empty_error_message(str(exc), fallback))


def _soft_result_error_payload(err: str) -> dict:
    return build_error_payload(
        ensure_non_empty_error_message(err, _GRAPHQL_RETURNED_ERRORS)
    )


class IntrospectionTools:
    """Registers MCP tools for schema introspection and ``execute_graphql``."""

    @staticmethod
    def register(mcp: MCPServer) -> None:
        """Register introspection-related tools on the MCP server."""

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
            meta=REMOTE,
        )
        async def introspect_type(
            type_name: str,
            ctx: Context,
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
            client = get_pipefy_client(ctx)
            try:
                result = await client.introspect_type(type_name, max_depth=max_depth)
            except Exception as exc:  # noqa: BLE001
                return _exception_error_payload(exc, _GRAPHQL_TOOL_REQUEST_FAILED)
            err = result.get("error")
            if isinstance(err, str):
                return _soft_result_error_payload(err)
            return build_success_payload(result, include_parsed=include_parsed)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
            meta=REMOTE,
        )
        async def introspect_mutation(
            mutation_name: str,
            ctx: Context,
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
            client = get_pipefy_client(ctx)
            try:
                result = await client.introspect_mutation(
                    mutation_name, max_depth=max_depth
                )
            except Exception as exc:  # noqa: BLE001
                return _exception_error_payload(exc, _GRAPHQL_TOOL_REQUEST_FAILED)
            err = result.get("error")
            if isinstance(err, str):
                return _soft_result_error_payload(err)
            return build_success_payload(result, include_parsed=include_parsed)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
            meta=REMOTE,
        )
        async def introspect_query(
            query_name: str,
            ctx: Context,
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
            client = get_pipefy_client(ctx)
            try:
                result = await client.introspect_query(query_name, max_depth=max_depth)
            except Exception as exc:  # noqa: BLE001
                return _exception_error_payload(exc, _GRAPHQL_TOOL_REQUEST_FAILED)
            err = result.get("error")
            if isinstance(err, str):
                return _soft_result_error_payload(err)
            return build_success_payload(result, include_parsed=include_parsed)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
            meta=REMOTE,
        )
        async def search_schema(
            keyword: str,
            ctx: Context,
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
            client = get_pipefy_client(ctx)
            try:
                result = await client.search_schema(keyword, kind=kind)
            except Exception as exc:  # noqa: BLE001
                return _exception_error_payload(exc, _GRAPHQL_TOOL_REQUEST_FAILED)
            err = result.get("error")
            if isinstance(err, str):
                return _soft_result_error_payload(err)
            return build_success_payload(result, include_parsed=include_parsed)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
            meta=REMOTE,
        )
        async def execute_graphql(
            query: str,
            ctx: Context,
            variables: dict[str, Any] | None = None,
            include_parsed: bool = False,
            confirm: bool = False,
            confirmation_token: str | None = None,
        ) -> dict:
            """Run arbitrary GraphQL against Pipefy (queries or mutations).

            Prefer dedicated tools when available. Use this as a fallback when no specific
            tool exists. Always introspect the mutation's input shape before executing.

            Mutations need a preview token: call once to receive ``confirmation_token``,
            then echo that token with ``confirm=True`` on step 2. A token is replayable
            within its TTL, so a non-idempotent mutation can run twice if the caller
            resends it.

            On ambiguous write failure (``success: false`` with empty or unclear message),
            re-read counts/ids before retrying; do not blind-retry creates.
            Queries and step-2 executions return ``result`` (pretty-printed JSON
            string). The step-1 mutation preview has no ``result`` key; it
            returns ``confirmation_token``. Set ``include_parsed=True`` to also
            get a ``data`` dict on executed responses.

            Args:
                query: Full GraphQL document (query or mutation).
                variables: Optional variable map for the operation.
                include_parsed: When True, include ``data`` dict alongside ``result``.
                confirm: Set to True with the preview token to execute a mutation (step 2).
                confirmation_token: Token from the preview response; echo it on step 2.
            """
            client = get_pipefy_client(ctx)
            inspection = inspect_graphql_document(query)
            if inspection.too_nested:
                return build_error_payload(
                    "GraphQL document is too deeply nested to parse."
                )
            if inspection.contains_mutation:
                guard = await check_destructive_confirmation(
                    ctx,
                    confirm=confirm,
                    resource_descriptor=inspection.mutation_descriptor,
                    irreversible_sentence=(
                        "⚠️ This GraphQL mutation's effects are permanent "
                        "and cannot be undone."
                    ),
                    resource_identity={
                        "document": hashlib.sha256(query.encode("utf-8")).hexdigest(),
                        "variables": hashlib.sha256(
                            json.dumps(
                                variables or {},
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        ).hexdigest(),
                    },
                    tool_name="execute_graphql",
                    confirmation_token=confirmation_token,
                )
                if guard is not None:
                    return guard
            try:
                result = await client.execute_graphql(query, variables)
            except Exception as exc:  # noqa: BLE001
                return _exception_error_payload(exc, _EXECUTE_GRAPHQL_FAILED)
            gql_errors = result.get("errors")
            if isinstance(gql_errors, list) and gql_errors:
                messages: list[str] = []
                for item in gql_errors:
                    if isinstance(item, dict):
                        msg = item.get("message")
                        if isinstance(msg, str):
                            stripped = msg.strip()
                            if stripped:
                                messages.append(stripped)
                text = "; ".join(messages) if messages else _GRAPHQL_RETURNED_ERRORS
                return build_error_payload(text)
            err = result.get("error")
            if isinstance(err, str):
                return _soft_result_error_payload(err)
            return build_success_payload(result, include_parsed=include_parsed)
