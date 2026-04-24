"""MCP tools for Pipefy database tables and records."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.services.pipefy.table_service import (
    UPDATE_TABLE_RECORD_ALLOWED_FIELD_KEYS,
    UPDATE_TABLE_RECORD_FIELDS_ERROR_MESSAGE,
)
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import (
    extract_graphql_correlation_id,
    extract_graphql_error_codes,
    with_debug_suffix,
)
from pipefy_mcp.tools.pagination_helpers import (
    build_pagination_info,
    validate_page_size,
)
from pipefy_mcp.tools.table_tool_helpers import (
    build_delete_table_error_payload,
    build_delete_table_success_payload,
    build_table_mutation_error_payload,
    build_table_mutation_success_payload,
    build_table_read_error_payload,
    build_table_read_success_payload,
    handle_table_tool_graphql_error,
    map_delete_table_error_to_message,
)
from pipefy_mcp.tools.tool_error_envelope import (
    is_unified_envelope_enabled,
    tool_error_message,
    tool_success,
)
from pipefy_mcp.tools.validation_helpers import (
    mutation_error_if_not_optional_dict,
    validate_optional_tool_id,
    validate_tool_id,
)

_TABLE_RECORDS_FIRST_MIN = 1
# ``table_records(first:)`` is capped at 200; align validator max with the API (not 500).
_TABLE_RECORDS_FIRST_MAX = 200
_SEARCH_TABLES_FIRST_MAX = 500


_CREATE_TABLE_EXTRA_RESERVED = frozenset({"name", "organization_id"})
_UPDATE_TABLE_EXTRA_RESERVED = frozenset({"id"})
_CREATE_TABLE_FIELD_EXTRA_RESERVED = frozenset({"table_id", "label", "type"})
_UPDATE_TABLE_FIELD_EXTRA_RESERVED = frozenset({"id"})


class TableTools:
    """MCP tools for database tables and records (reads and mutations)."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def search_tables(
            table_name: str | None = None,
            first: int = 100,
        ) -> dict[str, Any]:
            """Search for all accessible databases (tables) across all organizations.

            Use this tool to find a table's ID when you only know its name.
            Returns up to ``first`` tables per organization from the GraphQL connection
            (1-500, default 100). Optionally filtered by name client-side on that page.

            When filtering by name, uses substring matching first (score 100) and
            falls back to fuzzy matching with a 70% similarity threshold.
            Only tables with a match score of 70 or higher are included in results.
            Results are sorted by match score (best matches first).

            **Pagination.** The top-level ``pagination.has_more`` is always ``False``
            because this tool does not accept ``after``; the outer call is not
            paginable. Per-organization cursors live inside
            ``data.organizations[i].tables_page_end_cursor`` (set when that org has
            more rows than ``first``). The legacy ``search_limits.tables_has_next_page``
            key remains as an aggregate hint.

            Args:
                table_name: Optional table name to search for (case-insensitive partial match).
                first: GraphQL ``tables(first: ...)`` per organization (1-500).

            Returns:
                dict: Contains 'organizations' array, each with:
                      - id: Organization ID
                      - name: Organization name
                      - tables: Array of tables in the organization, each with:
                          - id: Table ID (use this for get_table, get_table_records, etc.)
                          - name: Table name
                          - description: Table description
                          - match_score: Match score (0-100) when table_name is provided,
                                         100 for substring matches, fuzzy score otherwise.
                      And ``search_limits`` (``tables_first``, ``tables_has_next_page``).
            """
            nfirst, err = validate_page_size(first, max_size=_SEARCH_TABLES_FIRST_MAX)
            if err is not None:
                return err
            raw = await client.search_tables(table_name, first=nfirst)
            if is_unified_envelope_enabled():
                return tool_success(
                    data=raw,
                    message="Tables search retrieved.",
                    pagination={
                        "has_more": False,
                        "end_cursor": None,
                        "page_size": nfirst,
                    },
                )
            return raw

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_table(table_id: PipefyId) -> dict[str, Any]:
            """Load one database table: name, description, fields, and authorization.

            Use this after ``search_tables`` (or when you already have a table ID) to inspect
            schema, field types, and permissions before creating or updating records.

            ``table_id`` is the **database table** id (from ``search_tables`` / ``get_tables``).
            For **table-to-table relation link** metadata, use ``get_table_relations`` with
            table-**relation** ids — not this argument.

            Args:
                table_id: Pipefy database table ID.

            Returns:
                On success, a structured payload with ``success``, ``message``, and ``data``
                (GraphQL ``table`` object: ``id``, ``name``, ``description``, ``table_fields``,
                ``authorization``). On validation or GraphQL errors, ``success: False`` with an
                ``error`` message.
            """
            table_id, err = validate_tool_id(table_id, "table_id")
            if err is not None:
                return build_table_read_error_payload(message=tool_error_message(err))
            try:
                raw = await client.get_table(table_id)
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Get table failed.",
                    resource_kind="table",
                    resource_id=str(table_id),
                )
            return build_table_read_success_payload(
                raw,
                message="Table metadata retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_tables(table_ids: list[PipefyId]) -> dict[str, Any]:
            """Load several database tables by ID (same shape as get_table per table).

            IDs are **database table** ids, not table-**relation** ids (see ``get_table_relations``).

            Args:
                table_ids: Non-empty list of table IDs.
            """
            if not isinstance(table_ids, list) or not table_ids:
                return build_table_read_error_payload(
                    message="Invalid 'table_ids': provide a non-empty list of IDs.",
                )
            cleaned_ids = []
            for tid in table_ids:
                cleaned, err = validate_tool_id(tid, "table_ids")
                if err is not None:
                    return build_table_read_error_payload(
                        message="Each table ID must be a non-empty string or positive integer.",
                    )
                cleaned_ids.append(cleaned)
            try:
                raw = await client.get_tables(cleaned_ids)
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Get tables failed.",
                    resource_kind="table",
                )
            return build_table_read_success_payload(
                raw,
                message="Tables metadata retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_table_records(
            table_id: PipefyId,
            first: int = 50,
            after: str | None = None,
        ) -> dict[str, Any]:
            """List records in a database table using cursor pagination.

            Use `pagination.hasNextPage` and `pagination.endCursor` from the response;
            pass `after=endCursor` on the next call to fetch the following page.
            Default page size is 50; maximum is 200.

            **Note:** The Pipefy API omits ``record_fields`` entries whose value is
            null or empty — the response only includes populated fields. To discover
            **all** fields defined on the table (including empty ones), call
            ``get_table`` and cross-reference its ``table_fields``.

            Args:
                table_id: Database table ID.
                first: Page size (1–200, default 50).
                after: Cursor from the previous page (`endCursor`), if any.
            """
            table_id, err = validate_tool_id(table_id, "table_id")
            if err is not None:
                return build_table_read_error_payload(message=tool_error_message(err))
            nfirst, page_err = validate_page_size(
                first, max_size=_TABLE_RECORDS_FIRST_MAX
            )
            if page_err is not None:
                return page_err
            if after is not None and (not isinstance(after, str) or not after.strip()):
                return build_table_read_error_payload(
                    message="Invalid 'after': omit or pass a non-empty cursor string.",
                )
            try:
                raw = await client.get_table_records(
                    table_id,
                    first=nfirst,
                    after=after.strip() if isinstance(after, str) else after,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "List table records failed.",
                    resource_kind="table",
                    resource_id=str(table_id),
                )
            if is_unified_envelope_enabled():
                page_info = (raw.get("table_records") or {}).get("pageInfo")
                return tool_success(
                    data=raw,
                    message="Table records page retrieved.",
                    pagination=build_pagination_info(
                        page_info=page_info, page_size=nfirst
                    ),
                )
            return build_table_read_success_payload(
                raw,
                message="Table records page retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_table_record(record_id: PipefyId) -> dict[str, Any]:
            """Load a single database table record with its field values.

            Use this when you have a record ID (e.g. from ``get_table_records`` or ``find_records``)
            and need the full row: title and ``record_fields`` name/value pairs.

            **Note:** The Pipefy API omits ``record_fields`` entries whose value is
            null or empty. To discover all fields defined on the table, call
            ``get_table`` and cross-reference its ``table_fields``.

            Args:
                record_id: Table record ID (string or positive integer).

            Returns:
                On success, ``success``, ``message``, and ``data`` containing the GraphQL
                ``table_record`` (``id``, ``title``, ``record_fields``). On errors,
                ``success: False`` with ``error``.
            """
            record_id, err = validate_tool_id(record_id, "record_id")
            if err is not None:
                return build_table_read_error_payload(message=tool_error_message(err))
            try:
                raw = await client.get_table_record(record_id)
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Get table record failed.",
                    resource_kind="table_record",
                    resource_id=str(record_id),
                )
            return build_table_read_success_payload(
                raw,
                message="Table record retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def find_records(
            table_id: PipefyId,
            field_id: str,
            field_value: str,
            first: int | None = None,
            after: str | None = None,
        ) -> dict[str, Any]:
            """Search records in a database table where a field matches a value.

            Uses Pipefy `findRecords` (returns card-shaped nodes with `fields`).
            Optional `first` / `after` follow the same cursor pattern as listing.

            Args:
                table_id: Database table ID.
                field_id: Field ID to filter on (from table metadata).
                field_value: Value to match (string; format depends on field type).
                first: Optional page size for pagination.
                after: Optional cursor from a previous response.
            """
            table_id, err = validate_tool_id(table_id, "table_id")
            if err is not None:
                return build_table_read_error_payload(message=tool_error_message(err))
            if not isinstance(field_id, str) or not field_id.strip():
                return build_table_read_error_payload(
                    message="Invalid 'field_id': provide a non-empty string.",
                )
            if not isinstance(field_value, str):
                return build_table_read_error_payload(
                    message="Invalid 'field_value': provide a string.",
                )
            if first is not None and (
                not isinstance(first, int)
                or first < _TABLE_RECORDS_FIRST_MIN
                or first > _TABLE_RECORDS_FIRST_MAX
            ):
                return build_table_read_error_payload(
                    message=(
                        "Invalid 'first': omit or use an integer between "
                        f"{_TABLE_RECORDS_FIRST_MIN} and {_TABLE_RECORDS_FIRST_MAX}."
                    ),
                )
            if after is not None and (not isinstance(after, str) or not after.strip()):
                return build_table_read_error_payload(
                    message="Invalid 'after': omit or pass a non-empty cursor string.",
                )
            try:
                raw = await client.find_records(
                    table_id,
                    field_id.strip(),
                    field_value,
                    first=first,
                    after=after.strip() if isinstance(after, str) else after,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Find records failed.",
                    resource_kind="table",
                    resource_id=str(table_id),
                )
            return build_table_read_success_payload(
                raw,
                message="Record search completed.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_table(
            name: str,
            organization_id: PipefyId,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a new database table in an organization.

            Args:
                name: Table name.
                organization_id: Owning organization ID.
                extra_input: Additional `CreateTableInput` fields (e.g. description, authorization).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            if not isinstance(name, str) or not name.strip():
                return build_table_mutation_error_payload(
                    message="Invalid 'name': provide a non-empty string.",
                )
            organization_id, err = validate_tool_id(organization_id, "organization_id")
            if err is not None:
                return build_table_mutation_error_payload(
                    message=tool_error_message(err)
                )
            bad_extra = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad_extra is not None:
                return bad_extra
            merged: dict[str, Any] = {}
            for k, v in (extra_input or {}).items():
                if k not in _CREATE_TABLE_EXTRA_RESERVED and v is not None:
                    merged[k] = v
            try:
                raw = await client.create_table(name.strip(), organization_id, **merged)
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Create table failed.",
                    debug=debug,
                    resource_kind="organization",
                    resource_id=str(organization_id),
                )
            return build_table_mutation_success_payload(
                message="Table created.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_table(
            table_id: PipefyId,
            name: str | None = None,
            description: str | None = None,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update database table attributes (name, description, or other `UpdateTableInput` fields).

            Args:
                table_id: Table ID to update.
                name: New name, if changing.
                description: New description, if changing.
                extra_input: Other `UpdateTableInput` keys to merge (e.g. public, icon).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            table_id, err = validate_tool_id(table_id, "table_id")
            if err is not None:
                return build_table_mutation_error_payload(
                    message=tool_error_message(err)
                )
            bad_extra = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad_extra is not None:
                return bad_extra
            if all(x is None for x in (name, description)) and not (
                extra_input and any(v is not None for v in extra_input.values())
            ):
                return build_table_mutation_error_payload(
                    message=(
                        "Provide at least one of: name, description, or non-null keys in extra_input."
                    ),
                )
            kwargs: dict[str, Any] = {}
            if name is not None:
                kwargs["name"] = name
            if description is not None:
                kwargs["description"] = description
            for k, v in (extra_input or {}).items():
                if k not in _UPDATE_TABLE_EXTRA_RESERVED and v is not None:
                    kwargs[k] = v
            try:
                raw = await client.update_table(table_id, **kwargs)
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Update table failed.",
                    debug=debug,
                    resource_kind="table",
                    resource_id=str(table_id),
                )
            return build_table_mutation_success_payload(
                message="Table updated.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_table(
            ctx: Context[ServerSession, None],
            table_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a database table permanently.

            Without confirmation, returns a preview and does not delete.
            Always confirm with the human user before calling with confirm=True.

            Args:
                table_id: Table ID to delete.
                confirm: When True, performs deletion after explicit user confirmation.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            table_id, err = validate_tool_id(table_id, "table_id")
            if err is not None:
                return build_delete_table_error_payload(message=tool_error_message(err))

            table_name = "Unknown"
            try:
                table_response = await client.get_table(table_id)
                table_data = table_response.get("table") or {}
                table_name = table_data.get("name") or "Unknown"
            except Exception as exc:  # noqa: BLE001
                codes = extract_graphql_error_codes(exc)
                correlation_id = extract_graphql_correlation_id(exc)
                base = map_delete_table_error_to_message(
                    table_id=table_id,
                    table_name=table_name,
                    codes=codes,
                )
                return build_delete_table_error_payload(
                    message=with_debug_suffix(
                        base,
                        debug=debug,
                        codes=codes,
                        correlation_id=correlation_id,
                    ),
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"table '{table_name}' (ID: {table_id})",
            )
            if guard is not None:
                return guard

            try:
                delete_response = await client.delete_table(table_id)
                success = (delete_response.get("deleteTable") or {}).get("success")
                if success:
                    return build_delete_table_success_payload(table_id=table_id)
                return build_delete_table_error_payload(
                    message=map_delete_table_error_to_message(
                        table_id=table_id,
                        table_name=table_name,
                        codes=[],
                    )
                )
            except Exception as exc:  # noqa: BLE001
                codes = extract_graphql_error_codes(exc)
                correlation_id = extract_graphql_correlation_id(exc)
                base = map_delete_table_error_to_message(
                    table_id=table_id,
                    table_name=table_name,
                    codes=codes,
                )
                return build_delete_table_error_payload(
                    message=with_debug_suffix(
                        base,
                        debug=debug,
                        codes=codes,
                        correlation_id=correlation_id,
                    ),
                )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_table_record(
            table_id: PipefyId,
            fields: Any,
            title: str | None = None,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a row in a database table with field values.

            Args:
                table_id: Target table ID.
                    Discover via: ``search_tables`` or ``get_tables(table_ids)``.
                fields: Map of field_id -> value, or list of objects with field_id / field_value.
                    Discover via: ``get_table(table_id).table_fields[].id``.
                title: Optional record title.
                extra_input: Other `CreateTableRecordInput` keys (e.g. label_ids).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            table_id, err = validate_tool_id(table_id, "table_id")
            if err is not None:
                return build_table_mutation_error_payload(
                    message=tool_error_message(err)
                )
            if not isinstance(fields, (dict, list)):
                return build_table_mutation_error_payload(
                    message="Invalid 'fields': provide a dict (field_id -> value) or a list of field objects.",
                )
            if isinstance(fields, dict) and len(fields) == 0:
                return build_table_mutation_error_payload(
                    message="Invalid 'fields': provide at least one field entry.",
                )
            if isinstance(fields, list) and len(fields) == 0:
                return build_table_mutation_error_payload(
                    message="Invalid 'fields': provide at least one field entry.",
                )
            if isinstance(fields, list):
                for i, item in enumerate(fields):
                    if not isinstance(item, dict):
                        return build_table_mutation_error_payload(
                            message=(
                                f"Invalid 'fields' at index {i}: each entry must be an "
                                "object with field_id and field_value."
                            ),
                        )
                    if "field_id" not in item or "field_value" not in item:
                        return build_table_mutation_error_payload(
                            message=(
                                f"Invalid 'fields' at index {i}: include field_id and "
                                "field_value."
                            ),
                        )
            bad_extra = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad_extra is not None:
                return bad_extra
            merged_attrs: dict[str, Any] = {}
            if title is not None:
                merged_attrs["title"] = title
            for k, v in (extra_input or {}).items():
                if v is not None:
                    merged_attrs[k] = v
            try:
                raw = await client.create_table_record(table_id, fields, **merged_attrs)
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Create table record failed.",
                    debug=debug,
                    resource_kind="table",
                    resource_id=str(table_id),
                )
            return build_table_mutation_success_payload(
                message="Table record created.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_table_record(
            record_id: PipefyId,
            fields: dict[str, Any],
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update a table record (title, due_date, status_id per Pipefy `UpdateTableRecordInput`).

            For custom field values, use set_table_record_field_value.

            Args:
                record_id: Record ID.
                    Discover via: ``find_records(table_id, field_id, field_value)`` or
                    ``get_table_records(table_id)[].id``.
                fields: Keys may include title, due_date, status_id (or statusId).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            record_id, err = validate_tool_id(record_id, "record_id")
            if err is not None:
                return build_table_mutation_error_payload(
                    message=tool_error_message(err)
                )
            if not isinstance(fields, dict) or not fields:
                return build_table_mutation_error_payload(
                    message="Invalid 'fields': provide a non-empty dict with at least one attribute.",
                )
            if not any(
                key in UPDATE_TABLE_RECORD_ALLOWED_FIELD_KEYS and value is not None
                for key, value in fields.items()
            ):
                return build_table_mutation_error_payload(
                    message=UPDATE_TABLE_RECORD_FIELDS_ERROR_MESSAGE,
                )
            try:
                raw = await client.update_table_record(record_id, fields)
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Update table record failed.",
                    debug=debug,
                    resource_kind="table_record",
                    resource_id=str(record_id),
                )
            return build_table_mutation_success_payload(
                message="Table record updated.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_table_record(
            ctx: Context[ServerSession, None],
            record_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a table record permanently.

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Args:
                record_id: Record ID to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            record_id, err = validate_tool_id(record_id, "record_id")
            if err is not None:
                return build_table_mutation_error_payload(
                    message=tool_error_message(err)
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"table record (ID: {record_id})",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_table_record(record_id)
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Delete table record failed.",
                    debug=debug,
                    resource_kind="table_record",
                    resource_id=str(record_id),
                )
            return build_table_mutation_success_payload(
                message="Table record deleted.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def set_table_record_field_value(
            record_id: PipefyId,
            field_id: PipefyId,
            value: Any,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update a single custom field on a table record.

            Args:
                record_id: Record ID.
                    Discover via: ``find_records(table_id, field_id, field_value)`` or
                    ``get_table_records(table_id)[].id``.
                field_id: Table field ID.
                    Discover via: ``get_table(table_id).table_fields[].id``.
                value: New value (string/number/list as required by the field type).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            record_id, err = validate_tool_id(record_id, "record_id")
            if err is not None:
                return build_table_mutation_error_payload(
                    message=tool_error_message(err)
                )
            field_id, err = validate_tool_id(field_id, "field_id")
            if err is not None:
                return build_table_mutation_error_payload(
                    message=tool_error_message(err)
                )
            if value is None:
                return build_table_mutation_error_payload(
                    message="Invalid 'value': cannot be null.",
                )
            try:
                raw = await client.set_table_record_field_value(
                    record_id, field_id, value
                )
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Set table record field value failed.",
                    debug=debug,
                    resource_kind="table_record",
                    resource_id=str(record_id),
                    invalid_args_hint="Use 'get_table' to list valid field IDs for this table.",
                )
            return build_table_mutation_success_payload(
                message="Field value updated.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_table_field(
            table_id: PipefyId,
            label: str,
            field_type: str,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Add a column (field) to a database table schema.

            Common field types: `short_text`, `long_text`, `number`, `date`, `datetime`,
            `currency`, `email`, `phone`, `select`, `radio_horizontal`, `radio_vertical`,
            `checklist_horizontal`, `checklist_vertical`, `label_select`, `assignee_select`,
            `attachment`, `connector`, `cpf`, `cnpj`, `time`, `due_date`, `id`, `statement`.

            For the complete list or new types, use `introspect_type("CreateTableFieldInput")`.

            Args:
                table_id: Database table ID.
                    Discover via: ``search_tables`` or ``get_tables(table_ids)``.
                label: Field label in the UI.
                field_type: Pipefy field type string (API input key `type`). See common types above.
                extra_input: Additional CreateTableFieldInput keys to merge (e.g. required, options).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            table_id, err = validate_tool_id(table_id, "table_id")
            if err is not None:
                return build_table_mutation_error_payload(
                    message=tool_error_message(err)
                )
            if not isinstance(label, str) or not label.strip():
                return build_table_mutation_error_payload(
                    message="Invalid 'label': provide a non-empty string.",
                )
            if not isinstance(field_type, str) or not field_type.strip():
                return build_table_mutation_error_payload(
                    message="Invalid 'field_type': provide a non-empty string.",
                )
            bad_extra = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad_extra is not None:
                return bad_extra
            merged: dict[str, Any] = {}
            for k, v in (extra_input or {}).items():
                if k not in _CREATE_TABLE_FIELD_EXTRA_RESERVED and v is not None:
                    merged[k] = v
            try:
                raw = await client.create_table_field(
                    table_id,
                    label.strip(),
                    field_type.strip(),
                    **merged,
                )
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Create table field failed.",
                    debug=debug,
                    resource_kind="table",
                    resource_id=str(table_id),
                )
            return build_table_mutation_success_payload(
                message="Table field created.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_table_field(
            field_id: PipefyId,
            table_id: PipefyId | None = None,
            label: str | None = None,
            description: str | None = None,
            required: bool | None = None,
            options: list[Any] | dict[str, Any] | None = None,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update a database table field (schema column).

            Pass only attributes to change. The `table_id` is required by the Pipefy API.

            Args:
                field_id: Table field ID (slug string or positive integer).
                table_id: Table ID containing this field (required by API). If not provided, can be passed via extra_input.
                label: New label, if changing.
                description: New description, if changing.
                required: Whether the field is required, if changing.
                options: Field options structure, if changing.
                extra_input: Other UpdateTableFieldInput keys to merge (e.g. table_id if not provided as parameter).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            field_id, err = validate_tool_id(field_id, "field_id")
            if err is not None:
                return build_table_mutation_error_payload(
                    message=tool_error_message(err)
                )
            ok, table_id, opt_err = validate_optional_tool_id(table_id, "table_id")
            if not ok:
                return build_table_mutation_error_payload(
                    message=tool_error_message(opt_err)
                )
            bad_extra = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad_extra is not None:
                return bad_extra
            update_attrs: dict[str, Any] = {
                k: v
                for k, v in (extra_input or {}).items()
                if k not in _UPDATE_TABLE_FIELD_EXTRA_RESERVED and v is not None
            }
            if label is not None:
                update_attrs["label"] = label
            if description is not None:
                update_attrs["description"] = description
            if required is not None:
                update_attrs["required"] = required
            if options is not None:
                update_attrs["options"] = options
            has_updates = bool(update_attrs) or any(
                x is not None for x in (label, description, required, options)
            )
            if not has_updates and table_id is None:
                return build_table_mutation_error_payload(
                    message="Provide at least one attribute to update and table_id (required by API).",
                )
            table_id_to_use = table_id
            if table_id_to_use is None and "table_id" in update_attrs:
                table_id_to_use = update_attrs.pop("table_id")
            if table_id_to_use is None and update_attrs:
                return build_table_mutation_error_payload(
                    message=(
                        "table_id is required by the API. Provide it as a parameter or via extra_input."
                    ),
                )
            try:
                raw = await client.update_table_field(
                    field_id, table_id=table_id_to_use, **update_attrs
                )
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Update table field failed.",
                    debug=debug,
                    resource_kind="table_field",
                    resource_id=str(field_id),
                )
            return build_table_mutation_success_payload(
                message="Table field updated.",
                data=raw,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_table_field(
            ctx: Context[ServerSession, None],
            field_id: PipefyId,
            table_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete a database table field (column) permanently.

            Two-step operation: preview with ``confirm=False`` (default), then execute with
            ``confirm=True`` after explicit human approval. Elicitation does not authorize
            deletion (only ``confirm=True`` does).

            Args:
                field_id: Table field ID to delete.
                table_id: Table ID containing this field (required by the Pipefy API).
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            field_id, err = validate_tool_id(field_id, "field_id")
            if err is not None:
                return build_table_mutation_error_payload(
                    message=tool_error_message(err)
                )
            table_id, err = validate_tool_id(table_id, "table_id")
            if err is not None:
                return build_table_mutation_error_payload(
                    message=tool_error_message(err)
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"table field (ID: {field_id})",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_table_field(field_id, table_id)
            except Exception as exc:  # noqa: BLE001
                return handle_table_tool_graphql_error(
                    exc,
                    "Delete table field failed.",
                    debug=debug,
                    resource_kind="table_field",
                    resource_id=str(field_id),
                )
            return build_table_mutation_success_payload(
                message="Table field deleted.",
                data=raw,
            )
