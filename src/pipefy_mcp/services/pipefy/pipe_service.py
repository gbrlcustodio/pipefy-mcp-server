from __future__ import annotations

from httpx_auth import OAuth2ClientCredentials
from rapidfuzz import fuzz

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.pipe_queries import (
    GET_PHASE_ALLOWED_MOVES_QUERY,
    GET_PHASE_FIELDS_QUERY,
    GET_PIPE_MEMBERS_QUERY,
    GET_PIPE_QUERY,
    GET_PIPE_WITH_PREFERENCES_QUERY,
    GET_START_FORM_FIELDS_QUERY,
    SEARCH_PIPES_QUERY,
)
from pipefy_mcp.settings import PipefySettings


class PipeService(BasePipefyClient):
    """Service for Pipe-related operations."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def get_pipe(self, pipe_id: str | int) -> dict:
        """Get a pipe by its ID, including phases, labels, and start form fields."""
        variables = {"pipe_id": str(pipe_id)}
        return await self.execute_query(GET_PIPE_QUERY, variables)

    async def get_pipe_with_preferences(self, pipe_id: str | int) -> dict:
        """Get a pipe including AI preferences, phases with fields, and start form fields.

        Args:
            pipe_id: Pipe ID.
        """
        variables = {"pipe_id": str(pipe_id)}
        return await self.execute_query(GET_PIPE_WITH_PREFERENCES_QUERY, variables)

    async def get_pipe_members(self, pipe_id: str | int) -> dict:
        """Get the members of a pipe."""
        variables = {"pipeId": str(pipe_id)}
        return await self.execute_query(GET_PIPE_MEMBERS_QUERY, variables)

    async def get_start_form_fields(
        self, pipe_id: str | int, required_only: bool = False
    ) -> dict:
        """Get the start form fields of a pipe.

        Args:
            pipe_id: The ID of the pipe.
            required_only: If True, returns only required fields. Default: False.

        Returns:
            dict: A dictionary containing the list of start form fields with their properties.
        """

        variables = {"pipe_id": str(pipe_id)}
        result = await self.execute_query(GET_START_FORM_FIELDS_QUERY, variables)

        fields = result.get("pipe", {}).get("start_form_fields", [])

        if not fields:
            return {
                "message": "This pipe has no start form fields configured.",
                "start_form_fields": [],
            }

        if required_only:
            fields = [field for field in fields if field.get("required")]

            if not fields:
                return {
                    "message": "This pipe has no required fields in the start form.",
                    "start_form_fields": [],
                }

        return {"start_form_fields": fields}

    async def search_pipes(
        self, pipe_name: str | None = None, match_threshold: int = 70
    ) -> dict:
        """Search for pipes across all organizations using fuzzy matching.

        Args:
            pipe_name: Optional pipe name to search for (fuzzy match).
                       Supports partial matches.
                       If not provided, returns all pipes.

        Returns:
            dict: A dictionary containing organizations with their pipes.
                  If pipe_name is provided, only pipes matching the name are included,
                  sorted by match score (best matches first).
        """
        result = await self.execute_query(SEARCH_PIPES_QUERY, {})

        organizations = result.get("organizations", [])

        if not pipe_name:
            return {"organizations": organizations}

        filtered_orgs = []

        for org in organizations:
            matching_pipes = []
            for pipe in org.get("pipes", []):
                pipe_display_name = pipe.get("name", "")
                if pipe_name.lower() in pipe_display_name.lower():
                    matching_pipes.append((100.0, pipe))
                else:
                    score = fuzz.WRatio(
                        pipe_name, pipe_display_name, score_cutoff=match_threshold
                    )
                    if score:
                        matching_pipes.append((score, pipe))

            if matching_pipes:
                matching_pipes.sort(key=lambda x: x[0], reverse=True)
                filtered_orgs.append(
                    {
                        "id": org.get("id"),
                        "name": org.get("name"),
                        "pipes": [
                            {**pipe, "match_score": round(score, 1)}
                            for score, pipe in matching_pipes
                        ],
                    }
                )

        return {"organizations": filtered_orgs}

    async def get_phase_allowed_move_targets(self, phase_id: str | int) -> dict:
        """List phases a card may move to from ``phase_id`` (UI transition rules).

        Read-only: mirrors Pipefy **Phase → Connections**. Returns the GraphQL
        ``phase`` object including ``cards_can_be_moved_to_phases``.

        Args:
            phase_id: Source phase ID.

        Returns:
            Raw GraphQL payload (``phase`` key at top level).
        """
        variables = {"phase_id": str(phase_id)}
        return await self.execute_query(GET_PHASE_ALLOWED_MOVES_QUERY, variables)

    async def get_phase_fields(
        self, phase_id: str | int, required_only: bool = False
    ) -> dict:
        """Get the fields available in a specific phase.

        Args:
            phase_id: The ID of the phase.
            required_only: If True, returns only required fields. Default: False.

        Returns:
            dict: A dictionary containing the phase info and its fields.
        """
        variables = {"phase_id": str(phase_id)}
        result = await self.execute_query(GET_PHASE_FIELDS_QUERY, variables)

        phase = result.get("phase", {})
        fields = phase.get("fields", [])

        empty_reason = ""

        if not fields:
            empty_reason = "This phase has no fields configured."
        elif required_only:
            fields = [field for field in fields if field.get("required")]
            if not fields:
                empty_reason = "This phase has no required fields."

        if empty_reason:
            return {
                "phase_id": phase.get("id"),
                "phase_name": phase.get("name"),
                "message": empty_reason,
                "fields": [],
            }

        return {
            "phase_id": phase.get("id"),
            "phase_name": phase.get("name"),
            "fields": fields,
        }
