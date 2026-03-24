from __future__ import annotations

from httpx_auth import OAuth2ClientCredentials
from rapidfuzz import fuzz

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.database_queries import (
    GET_TABLE_QUERY,
    GET_TABLE_RECORD_QUERY,
    GET_TABLE_RECORDS_QUERY,
    SEARCH_TABLES_QUERY,
)
from pipefy_mcp.settings import PipefySettings


class DatabaseService(BasePipefyClient):
    """Service for Pipefy Database (Table) read operations."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def get_table(self, table_id: str) -> dict:
        """Get a database (table) by its ID, including its fields schema.

        Args:
            table_id: The ID of the table.

        Returns:
            dict: Table metadata with id, name, description, and fields.
        """
        variables = {"id": table_id}
        return await self.execute_query(GET_TABLE_QUERY, variables)

    async def get_table_records(
        self,
        table_id: str,
        first: int = 50,
        after: str | None = None,
    ) -> dict:
        """Get records from a database (table) with cursor-based pagination.

        Args:
            table_id: The ID of the table.
            first: Number of records to return. Default: 50.
            after: Cursor for pagination (endCursor from a previous response).

        Returns:
            dict: Records with their fields, total count, and page info.
        """
        variables: dict = {"table_id": table_id, "first": first}
        if after:
            variables["after"] = after

        result = await self.execute_query(GET_TABLE_RECORDS_QUERY, variables)

        connection = result.get("table_records", {})
        page_info = connection.get("pageInfo", {})

        return {
            "records": connection.get("nodes", []),
            "total_count": connection.get("totalCount", 0),
            "has_next_page": page_info.get("hasNextPage", False),
            "end_cursor": page_info.get("endCursor"),
        }

    async def get_table_record(self, record_id: str) -> dict:
        """Get a specific database record by its ID.

        Args:
            record_id: The ID of the record.

        Returns:
            dict: Record data with id, title, timestamps, and field values.
        """
        variables = {"id": record_id}
        result = await self.execute_query(GET_TABLE_RECORD_QUERY, variables)
        return result.get("table_record", {})

    async def search_tables(
        self, table_name: str | None = None, match_threshold: int = 70
    ) -> dict:
        """Search for databases (tables) across all organizations using fuzzy matching.

        Args:
            table_name: Optional table name to search for (fuzzy match).
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
