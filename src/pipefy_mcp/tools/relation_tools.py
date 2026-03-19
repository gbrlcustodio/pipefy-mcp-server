"""MCP tools for Pipefy pipe/table relations, pipe-relation CRUD, and card relations."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.relation_tool_helpers import (
    build_relation_error_payload,
    build_relation_mutation_success_payload,
    build_relation_read_success_payload,
    handle_relation_tool_graphql_error,
)
from pipefy_mcp.tools.validation_helpers import (
    mutation_error_if_not_optional_dict,
    valid_repo_id,
)


class RelationTools:
    """MCP tools for relations between pipes/tables and linked cards."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_pipe_relations(pipe_id: str | int) -> dict[str, Any]:
            """List pipe relations for a pipe (parent and child links, config, and repo refs).

            Args:
                pipe_id: Pipe ID.
            """
            if not valid_repo_id(pipe_id):
                return build_relation_error_payload(
                    message="Invalid 'pipe_id': provide a non-empty string or positive integer.",
                )
            try:
                raw = await client.get_pipe_relations(pipe_id)
            except Exception as exc:
                return handle_relation_tool_graphql_error(
                    exc, "Get pipe relations failed."
                )
            return build_relation_read_success_payload(
                raw,
                message="Pipe relations retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_table_relations(relation_ids: list[str | int]) -> dict[str, Any]:
            """Load table relations by their IDs (Pipefy root `table_relations`).

            Args:
                relation_ids: Non-empty list of **table relation** IDs (not the database table ID).
            """
            if not isinstance(relation_ids, list) or not relation_ids:
                return build_relation_error_payload(
                    message="Invalid 'relation_ids': provide a non-empty list of table relation IDs.",
                )
            if not all(valid_repo_id(rid) for rid in relation_ids):
                return build_relation_error_payload(
                    message="Each relation ID must be a non-empty string or positive integer.",
                )
            try:
                raw = await client.get_table_relations(relation_ids)
            except Exception as exc:
                return handle_relation_tool_graphql_error(
                    exc, "Get table relations failed."
                )
            return build_relation_read_success_payload(
                raw,
                message="Table relations retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_pipe_relation(
            parent_id: str | int,
            child_id: str | int,
            name: str,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a parent-child relation between two pipes.

            Optional ``extra_input`` merges into Pipefy ``CreatePipeRelationInput`` (camelCase keys), e.g. ``canCreateNewItems``, ``ownFieldMaps``.

            Args:
                parent_id: Parent pipe ID.
                child_id: Child pipe ID.
                name: Relation name/label.
                extra_input: Optional extra fields for the mutation input.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_repo_id(parent_id) or not valid_repo_id(child_id):
                return build_relation_error_payload(
                    message="Invalid 'parent_id' or 'child_id': use non-empty strings or positive integers.",
                )
            if not isinstance(name, str) or not name.strip():
                return build_relation_error_payload(
                    message="Invalid 'name': provide a non-empty string.",
                )
            bad = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad is not None:
                return bad
            try:
                raw = await client.create_pipe_relation(
                    parent_id,
                    child_id,
                    name.strip(),
                    extra_input=extra_input,
                )
            except Exception as exc:
                return handle_relation_tool_graphql_error(
                    exc, "Create pipe relation failed.", debug=debug
                )
            return build_relation_mutation_success_payload(
                message="Pipe relation created.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_pipe_relation(
            relation_id: str | int,
            name: str,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update an existing pipe relation (name, auto-fill, connection flags).

            Optional ``extra_input`` merges into Pipefy ``UpdatePipeRelationInput`` (camelCase keys), overriding defaults for flags or ``ownFieldMaps``.

            Args:
                relation_id: Pipe relation ID.
                name: New relation name (required by the API).
                extra_input: Optional extra fields for the mutation input.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_repo_id(relation_id):
                return build_relation_error_payload(
                    message="Invalid 'relation_id': use a non-empty string or positive integer.",
                )
            if not isinstance(name, str) or not name.strip():
                return build_relation_error_payload(
                    message="Invalid 'name': provide a non-empty string.",
                )
            bad = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad is not None:
                return bad
            try:
                raw = await client.update_pipe_relation(
                    relation_id,
                    name.strip(),
                    extra_input=extra_input,
                )
            except Exception as exc:
                return handle_relation_tool_graphql_error(
                    exc, "Update pipe relation failed.", debug=debug
                )
            return build_relation_mutation_success_payload(
                message="Pipe relation updated.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_pipe_relation(
            relation_id: str | int,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Permanently delete a pipe relation by ID.

            Always confirm with the user before calling — deletion cannot be undone.

            Args:
                relation_id: Pipe relation ID to delete.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_repo_id(relation_id):
                return build_relation_error_payload(
                    message="Invalid 'relation_id': use a non-empty string or positive integer.",
                )
            try:
                raw = await client.delete_pipe_relation(relation_id)
            except Exception as exc:
                return handle_relation_tool_graphql_error(
                    exc, "Delete pipe relation failed.", debug=debug
                )
            return build_relation_mutation_success_payload(
                message="Pipe relation deleted.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_card_relation(
            parent_id: str | int,
            child_id: str | int,
            source_id: str | int,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Connect a child card to a parent card using an existing pipe relation.

            Use ``get_pipe_relations`` on the parent or child pipe to obtain the pipe relation ``id`` (pass it as ``source_id``).

            Args:
                parent_id: Parent card ID.
                child_id: Child card ID.
                source_id: Pipe relation ID that defines the parent/child pipe link.
                extra_input: Optional ``CreateCardRelationInput`` fields (camelCase), e.g. ``sourceType`` (default ``PipeRelation``).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not valid_repo_id(parent_id) or not valid_repo_id(child_id):
                return build_relation_error_payload(
                    message="Invalid 'parent_id' or 'child_id': use non-empty strings or positive integers.",
                )
            if not valid_repo_id(source_id):
                return build_relation_error_payload(
                    message="Invalid 'source_id': use a non-empty string or positive integer (pipe relation ID).",
                )
            bad = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad is not None:
                return bad
            try:
                raw = await client.create_card_relation(
                    parent_id,
                    child_id,
                    source_id,
                    extra_input=extra_input,
                )
            except Exception as exc:
                return handle_relation_tool_graphql_error(
                    exc, "Create card relation failed.", debug=debug
                )
            return build_relation_mutation_success_payload(
                message="Card relation created.",
                data=raw,
            )
