from __future__ import annotations

from gql import Client

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.pipe_queries import (
    GET_PIPE_QUERY,
    GET_START_FORM_FIELDS_QUERY,
)


class PipeService(BasePipefyClient):
    """Service for Pipe-related operations."""

    def __init__(self, client: Client) -> None:
        super().__init__(client=client)

    async def get_pipe(self, pipe_id: int) -> dict:
        """Get a pipe by its ID, including phases, labels, and start form fields."""
        variables = {"pipe_id": pipe_id}
        return await self.execute_query(GET_PIPE_QUERY, variables)

    async def get_start_form_fields(
        self, pipe_id: int, required_only: bool = False
    ) -> dict:
        """Get the start form fields of a pipe.

        Args:
            pipe_id: The ID of the pipe.
            required_only: If True, returns only required fields. Default: False.

        Returns:
            dict: A dictionary containing the list of start form fields with their properties.
        """

        variables = {"pipe_id": pipe_id}
        result = await self.execute_query(GET_START_FORM_FIELDS_QUERY, variables)

        # Extract fields from result
        fields = result.get("pipe", {}).get("start_form_fields", [])

        # Handle empty start form (no fields configured at all)
        if not fields:
            return {
                "message": "This pipe has no start form fields configured.",
                "start_form_fields": [],
            }

        # Filter for required fields only if requested
        if required_only:
            fields = [field for field in fields if field.get("required")]

            # Handle case where no required fields exist after filtering
            if not fields:
                return {
                    "message": "This pipe has no required fields in the start form.",
                    "start_form_fields": [],
                }

        return {"start_form_fields": fields}
