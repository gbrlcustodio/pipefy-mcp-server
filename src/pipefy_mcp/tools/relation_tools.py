"""MCP tools for Pipefy pipe/table relations, pipe-relation CRUD, and card relations."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.relation_tool_helpers import (
    build_relation_error_payload,
    build_relation_mutation_success_payload,
    build_relation_read_success_payload,
    handle_relation_tool_graphql_error,
)
from pipefy_mcp.tools.validation_helpers import (
    mutation_error_if_not_optional_dict,
    validate_tool_id,
)


class RelationTools:
    """MCP tools for relations between pipes/tables and linked cards."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_pipe_relations(pipe_id: PipefyId) -> dict[str, Any]:
            """List pipe relations for a pipe (parent and child links, config, and repo refs).

            Takes a **pipe** ID. Each relation's ``id`` in the response is a **pipe relation**
            ID (use as ``source_id`` in ``create_card_relation``). Do not confuse with
            ``get_table_relations``, which takes **table relation** IDs, not ``pipe_id``.

            Args:
                pipe_id: Pipe ID.
            """
            pipe_id, err = validate_tool_id(pipe_id, "pipe_id")
            if err is not None:
                return err
            try:
                raw = await client.get_pipe_relations(pipe_id)
            except Exception as exc:  # noqa: BLE001
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
        async def get_table_relations(relation_ids: list[PipefyId]) -> dict[str, Any]:
            """Load table relations by ID (Pipefy root ``table_relations``).

            **Do not pass** ``table_id`` or a database table ID — this tool only accepts
            **table relation** identifiers (the link object between tables). To resolve
            table IDs for schema/records, use ``get_table`` / ``search_tables`` instead.
            Obtain table-relation IDs from the Pipefy UI, your saved metadata, or GraphQL
            (e.g. introspection / ``execute_graphql``), not from ``get_pipe_relations``.

            Args:
                relation_ids: Non-empty list of **table relation** IDs (never the database table ID).
            """
            if not isinstance(relation_ids, list) or not relation_ids:
                return build_relation_error_payload(
                    message="Invalid 'relation_ids': provide a non-empty list of table relation IDs.",
                )
            validated_ids = []
            for rid in relation_ids:
                cleaned, err = validate_tool_id(rid, "relation_id")
                if err is not None:
                    return err
                validated_ids.append(cleaned)
            try:
                raw = await client.get_table_relations(validated_ids)
            except Exception as exc:  # noqa: BLE001
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
            parent_id: PipefyId,
            child_id: PipefyId,
            name: str,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a parent-child relation between two pipes.

            ``parent_id`` and ``child_id`` are **pipe** IDs (not table or card IDs).
            Optional ``extra_input`` merges into Pipefy ``CreatePipeRelationInput`` (camelCase keys), e.g. ``canCreateNewItems``, ``ownFieldMaps``.

            Args:
                parent_id: Parent pipe ID.
                child_id: Child pipe ID.
                name: Relation name/label.
                extra_input: Optional extra fields for the mutation input.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            parent_id, err = validate_tool_id(parent_id, "parent_id")
            if err is not None:
                return err
            child_id, err = validate_tool_id(child_id, "child_id")
            if err is not None:
                return err
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
            except Exception as exc:  # noqa: BLE001
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
            relation_id: PipefyId,
            name: str,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update an existing pipe relation (name, auto-fill, connection flags).

            ``relation_id`` is the **pipe relation** id from ``get_pipe_relations`` (not a table relation id).
            Optional ``extra_input`` merges into Pipefy ``UpdatePipeRelationInput`` (camelCase keys), overriding defaults for flags or ``ownFieldMaps``.

            Args:
                relation_id: Pipe relation ID.
                name: New relation name (required by the API).
                extra_input: Optional extra fields for the mutation input.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            relation_id, err = validate_tool_id(relation_id, "relation_id")
            if err is not None:
                return err
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
            except Exception as exc:  # noqa: BLE001
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
            ctx: Context[ServerSession, None],
            relation_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Permanently delete a pipe relation by ID.

            ``relation_id`` is the **pipe relation** id from ``get_pipe_relations`` (not a table relation id).
            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Args:
                relation_id: Pipe relation ID to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            relation_id, err = validate_tool_id(relation_id, "relation_id")
            if err is not None:
                return err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"pipe relation (ID: {relation_id})",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_pipe_relation(relation_id)
            except Exception as exc:  # noqa: BLE001
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
            parent_id: PipefyId,
            child_id: PipefyId,
            source_id: PipefyId,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Connect a child card to a parent card using an existing pipe relation.

            ``source_id`` must be a **pipe relation** id from ``get_pipe_relations`` (the link between pipes).
            It is **not** a table-relation id (``get_table_relations``), not a database ``table_id``, and not a pipe or card id.

            Args:
                parent_id: Parent card ID.
                child_id: Child card ID.
                source_id: Pipe relation ID that defines the parent/child pipe link.
                extra_input: Optional ``CreateCardRelationInput`` fields (camelCase), e.g. ``sourceType`` (default ``PipeRelation``).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            parent_id, err = validate_tool_id(parent_id, "parent_id")
            if err is not None:
                return err
            child_id, err = validate_tool_id(child_id, "child_id")
            if err is not None:
                return err
            source_id, err = validate_tool_id(source_id, "source_id")
            if err is not None:
                return err
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
            except Exception as exc:  # noqa: BLE001
                return handle_relation_tool_graphql_error(
                    exc, "Create card relation failed.", debug=debug
                )
            return build_relation_mutation_success_payload(
                message="Card relation created.",
                data=raw,
            )
