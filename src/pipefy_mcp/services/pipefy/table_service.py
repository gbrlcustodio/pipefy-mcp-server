"""GraphQL queries for Pipefy database tables, records, and search."""

from __future__ import annotations

from typing import Any

from httpx_auth import OAuth2ClientCredentials
from rapidfuzz import fuzz

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.table_queries import (
    CREATE_TABLE_FIELD_MUTATION,
    CREATE_TABLE_MUTATION,
    CREATE_TABLE_RECORD_MUTATION,
    DELETE_TABLE_FIELD_MUTATION,
    DELETE_TABLE_MUTATION,
    DELETE_TABLE_RECORD_MUTATION,
    FIND_RECORDS_QUERY,
    GET_TABLE_QUERY,
    GET_TABLE_RECORD_QUERY,
    GET_TABLE_RECORDS_QUERY,
    GET_TABLES_QUERY,
    SEARCH_TABLES_QUERY,
    SET_TABLE_RECORD_FIELD_VALUE_MUTATION,
    UPDATE_TABLE_FIELD_MUTATION,
    UPDATE_TABLE_MUTATION,
    UPDATE_TABLE_RECORD_MUTATION,
)
from pipefy_mcp.services.pipefy.utils.formatters import convert_fields_to_array
from pipefy_mcp.settings import PipefySettings

UPDATE_TABLE_RECORD_ALLOWED_FIELD_KEYS = frozenset(
    {"title", "due_date", "status_id", "statusId"}
)
UPDATE_TABLE_RECORD_FIELDS_ERROR_MESSAGE = (
    "Invalid 'fields': provide at least one of title, due_date, status_id/statusId."
)


class TableService(BasePipefyClient):
    """Database table and record operations (reads, mutations, and field CRUD)."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def get_table(self, table_id: str | int) -> dict[str, Any]:
        """Fetch one database table by ID (metadata and fields)."""
        return await self.execute_query(GET_TABLE_QUERY, {"id": table_id})

    async def get_tables(self, table_ids: list[str | int]) -> dict[str, Any]:
        """Fetch multiple database tables by ID."""
        return await self.execute_query(GET_TABLES_QUERY, {"ids": list(table_ids)})

    async def get_table_records(
        self,
        table_id: str | int,
        first: int = 50,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List records for a table with cursor pagination (`table_records` root query).

        Args:
            table_id: Database table ID.
            first: Page size (forwarded to the API; callers may cap, e.g. max 200).
            after: Opaque cursor from the previous page's `pageInfo.endCursor`.
        """
        variables: dict[str, Any] = {"tableId": table_id, "first": first}
        if after is not None:
            variables["after"] = after
        return await self.execute_query(GET_TABLE_RECORDS_QUERY, variables)

    async def get_table_record(self, record_id: str | int) -> dict[str, Any]:
        """Fetch a single table record by ID."""
        return await self.execute_query(GET_TABLE_RECORD_QUERY, {"id": record_id})

    async def find_records(
        self,
        table_id: str | int,
        field_id: str,
        field_value: str,
        first: int | None = None,
        after: str | None = None,
    ) -> dict[str, Any]:
        """Search table records by field value via `findRecords` (Pipefy root query).

        Args:
            table_id: Database table ID (coerced to string for the API).
            field_id: Table field identifier to match.
            field_value: Value to match (string as expected by the field type).
            first: Optional page size.
            after: Optional cursor for pagination.
        """
        variables: dict[str, Any] = {
            "tableId": str(table_id),
            "fieldId": field_id,
            "fieldValue": field_value,
        }
        if first is not None:
            variables["first"] = first
        if after is not None:
            variables["after"] = after
        return await self.execute_query(FIND_RECORDS_QUERY, variables)

    async def create_table(
        self, name: str, organization_id: int, **attrs: Any
    ) -> dict[str, Any]:
        """Create a database table (`CreateTableInput` fields via ``**attrs`` when not None)."""
        input_obj: dict[str, Any] = {
            "name": name,
            "organization_id": organization_id,
        }
        for key, value in attrs.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(CREATE_TABLE_MUTATION, {"input": input_obj})

    async def update_table(self, table_id: str | int, **attrs: Any) -> dict[str, Any]:
        """Update a database table by ID. Pass only `UpdateTableInput` fields (omit or None to skip)."""
        payload: dict[str, Any] = {"id": table_id}
        for key, value in attrs.items():
            if value is not None:
                payload[key] = value
        return await self.execute_query(UPDATE_TABLE_MUTATION, {"input": payload})

    async def delete_table(self, table_id: str | int) -> dict[str, Any]:
        """Delete a database table by ID (permanent). Caller must enforce preview/confirm UX."""
        return await self.execute_query(
            DELETE_TABLE_MUTATION,
            {"input": {"id": table_id}},
        )

    async def create_table_record(
        self,
        table_id: str | int,
        fields: dict[str, Any] | list[dict[str, Any]],
        **attrs: Any,
    ) -> dict[str, Any]:
        """Create a record in a database table.

        Args:
            table_id: Target table ID.
            fields: Field values as a dict (field_id → value) or list of `FieldValueInput` dicts.
            **attrs: Other `CreateTableRecordInput` keys (e.g. title, assignee_ids), when not None.
        """
        input_obj: dict[str, Any] = {
            "table_id": table_id,
            "fields_attributes": convert_fields_to_array(fields),
        }
        for key, value in attrs.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            CREATE_TABLE_RECORD_MUTATION,
            {"input": input_obj},
        )

    async def update_table_record(
        self,
        record_id: str | int,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a table record. Only API-supported keys are sent: title, due_date, statusId.

        Args:
            record_id: Record ID.
            fields: May include ``title``, ``due_date``, ``status_id`` or ``statusId``.
        """
        if not any(
            key in UPDATE_TABLE_RECORD_ALLOWED_FIELD_KEYS and value is not None
            for key, value in fields.items()
        ):
            raise ValueError(UPDATE_TABLE_RECORD_FIELDS_ERROR_MESSAGE)
        payload: dict[str, Any] = {"id": record_id}
        for key, value in fields.items():
            if value is None:
                continue
            if key == "status_id":
                payload["statusId"] = value
            elif key in ("title", "due_date", "statusId"):
                payload[key] = value
        return await self.execute_query(
            UPDATE_TABLE_RECORD_MUTATION,
            {"input": payload},
        )

    async def delete_table_record(self, record_id: str | int) -> dict[str, Any]:
        """Delete a table record by ID (permanent)."""
        return await self.execute_query(
            DELETE_TABLE_RECORD_MUTATION,
            {"input": {"id": record_id}},
        )

    async def set_table_record_field_value(
        self,
        record_id: str | int,
        field_id: str | int,
        value: Any,
    ) -> dict[str, Any]:
        """Set one field on a table record (`value` is wrapped in a list if not already a list)."""
        api_value = value if isinstance(value, list) else [value]
        return await self.execute_query(
            SET_TABLE_RECORD_FIELD_VALUE_MUTATION,
            {
                "input": {
                    "table_record_id": record_id,
                    "field_id": field_id,
                    "value": api_value,
                }
            },
        )

    async def create_table_field(
        self,
        table_id: str | int,
        label: str,
        field_type: str,
        **attrs: Any,
    ) -> dict[str, Any]:
        """Add a column to a database table schema.

        Args:
            table_id: Table that will receive the field.
            label: Field label shown in the UI.
            field_type: Pipefy field type string (mapped to `type` on `CreateTableFieldInput`).
            **attrs: Other input fields (e.g. description, required, options), when not None.
        """
        input_obj: dict[str, Any] = {
            "table_id": table_id,
            "label": label,
            "type": field_type,
        }
        for key, value in attrs.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            CREATE_TABLE_FIELD_MUTATION,
            {"input": input_obj},
        )

    async def update_table_field(
        self, field_id: str | int, table_id: str | int | None = None, **attrs: Any
    ) -> dict[str, Any]:
        """Update a table field by ID (only non-None ``UpdateTableFieldInput`` keys are sent).

        Args:
            field_id: Table field ID.
            table_id: Table ID containing this field (required by API; if not provided, must be in attrs).
            **attrs: Attributes to change (omit or pass None to skip). If table_id is not provided as a parameter, it can be passed here.
        """
        payload: dict[str, Any] = {"id": field_id}
        if table_id is not None:
            payload["table_id"] = table_id
        for key, value in attrs.items():
            if value is not None:
                payload[key] = value
        return await self.execute_query(
            UPDATE_TABLE_FIELD_MUTATION,
            {"input": payload},
        )

    async def delete_table_field(self, field_id: str | int) -> dict[str, Any]:
        """Delete a table field by ID (permanent).

        Args:
            field_id: Field ID to remove from the table schema.
        """
        return await self.execute_query(
            DELETE_TABLE_FIELD_MUTATION,
            {"input": {"id": field_id}},
        )

    async def search_tables(
        self, table_name: str | None = None, match_threshold: int = 70
    ) -> dict[str, Any]:
        """Search for databases (tables) across all organizations using fuzzy matching.

        Args:
            table_name: Optional table name to search for (fuzzy match).
                        Supports partial matches.
                        If not provided, returns all tables.
            match_threshold: Minimum fuzzy match score (0-100). Default: 70.

        Returns:
            dict: Organizations with their matching tables, sorted by match score.
        """
        result = await self.execute_query(SEARCH_TABLES_QUERY, {})
        organizations = result.get("organizations", [])

        if not table_name:
            return {
                "organizations": [
                    {
                        "id": org.get("id"),
                        "name": org.get("name"),
                        "tables": org.get("tables", {}).get("nodes", []),
                    }
                    for org in organizations
                ]
            }

        filtered_orgs = []

        for org in organizations:
            matching_tables = []
            for table in org.get("tables", {}).get("nodes", []):
                table_display_name = table.get("name", "")
                score = fuzz.WRatio(
                    table_name, table_display_name, score_cutoff=match_threshold
                )
                if score:
                    matching_tables.append((score, table))

            if matching_tables:
                matching_tables.sort(key=lambda x: x[0], reverse=True)
                filtered_orgs.append(
                    {
                        "id": org.get("id"),
                        "name": org.get("name"),
                        "tables": [
                            {**table, "match_score": round(score, 1)}
                            for score, table in matching_tables
                        ],
                    }
                )

        return {"organizations": filtered_orgs}
