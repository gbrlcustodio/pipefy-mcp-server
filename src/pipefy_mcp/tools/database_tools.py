from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from pipefy_mcp.services.pipefy import PipefyClient


class DatabaseTools:
    """Declares tools to be used in the Database (Table) context."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        """Register the database tools in the MCP server."""

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def search_tables(table_name: str | None = None) -> dict:
            """
            Search for databases (tables) across all organizations.

            Args:
                table_name: Optional name to search for (fuzzy match, 70% threshold).
                            If not provided, returns all tables in all organizations.
            """
            return await client.search_tables(table_name)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_table(table_id: str) -> dict:
            """
            Get a database (table) structure by its ID.

            Returns the table metadata and its field definitions (id, label, type,
            required, options), which can be used to understand the schema before
            fetching records.

            Args:
                table_id: The ID of the database (table).
            """
            return await client.get_table(table_id)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_table_records(
            table_id: str,
            first: int = 50,
            after: str | None = None,
        ) -> dict:
            """
            Get records from a database (table) with cursor-based pagination.

            Returns a list of records with their id, title, status, timestamps, and
            field values (name + value pairs). The response includes `has_next_page`
            and `end_cursor` for fetching subsequent pages.

            Use `get_table` first to understand the field schema.

            Args:
                table_id: The ID of the database (table).
                first: Number of records to return (max 50). Default: 50.
                after: Cursor from `end_cursor` of a previous response, for pagination.
            """
            return await client.get_table_records(table_id, first, after)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_table_record(record_id: str) -> dict:
            """
            Get a specific database record by its ID.

            Returns the record's id, title, timestamps, and all field values.

            Args:
                record_id: The ID of the record.
            """
            return await client.get_table_record(record_id)
