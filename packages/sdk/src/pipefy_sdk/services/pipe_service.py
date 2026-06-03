from __future__ import annotations

from typing import Any

from httpx import Auth
from pipefy_infra.coerce import optional_int
from rapidfuzz import fuzz

from pipefy_sdk.base_client import BasePipefyClient
from pipefy_sdk.models.field_definition import parse_field_definitions
from pipefy_sdk.pipe_inventory import enrich_pipe_get_pipe_inventory
from pipefy_sdk.queries.pipe_queries import (
    GET_PHASE_ALLOWED_MOVES_QUERY,
    GET_PHASE_CARDS_COUNT_QUERY,
    GET_PHASE_CARDS_QUERY,
    GET_PHASE_FIELDS_QUERY,
    GET_PIPE_MEMBERS_QUERY,
    GET_PIPE_QUERY,
    GET_PIPE_WITH_PREFERENCES_QUERY,
    GET_START_FORM_FIELDS_QUERY,
    SEARCH_PIPES_QUERY,
)
from pipefy_sdk.settings import PipefySettings

SEARCH_PIPES_MAX_PER_ORG_CAP: int = 500
SEARCH_PIPES_MAX_PER_ORG_MIN: int = 1


def _clamp_max_pipes_per_org(value: int) -> int:
    return max(SEARCH_PIPES_MAX_PER_ORG_MIN, min(SEARCH_PIPES_MAX_PER_ORG_CAP, value))


class PipeService(BasePipefyClient):
    """Service for Pipe-related operations."""

    def __init__(
        self,
        settings: PipefySettings,
        *,
        auth: Auth,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def get_pipe(self, pipe_id: str | int) -> dict:
        """Get a pipe by its ID, including phases, labels, and start form fields.

        Normalizes inventory fields: ``start_form_phase`` (id, name, cards_count) when
        ``startFormPhaseId`` is set, and ``cards_count`` on each workflow phase in
        ``phases`` (start form excluded from ``phases``).
        """
        variables = {"pipe_id": str(pipe_id)}
        result = await self.execute_query(GET_PIPE_QUERY, variables)
        pipe = result.get("pipe")
        if not isinstance(pipe, dict):
            return result
        start_form_row: dict | None = None
        start_id = pipe.get("startFormPhaseId")
        if start_id is not None:
            start_id_str = str(start_id)
            phases = pipe.get("phases") or []
            if not any(
                isinstance(p, dict) and str(p.get("id")) == start_id_str for p in phases
            ):
                start_form_row = await self._fetch_phase_cards_count_row(start_id)
        return {
            **result,
            "pipe": enrich_pipe_get_pipe_inventory(
                pipe, start_form_phase_row=start_form_row
            ),
        }

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

        if fields:
            fields = parse_field_definitions(fields, action="return start form fields")

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
        self,
        pipe_name: str | None = None,
        *,
        # 70: WRatio score_cutoff default - balanced manually for typo/abbrev. recall vs. spurious matches.
        match_threshold: int = 70,
        max_pipes_per_org: int = SEARCH_PIPES_MAX_PER_ORG_CAP,
    ) -> dict:
        """Search for pipes across all organizations using fuzzy matching.

        Args:
            pipe_name: Optional pipe name to search for (fuzzy match).
                       Supports partial matches.
                       If not provided, returns pipes up to ``max_pipes_per_org`` each org.
            match_threshold: Minimum fuzzy score (0--100) when ``pipe_name`` is set.
            max_pipes_per_org: Max pipes returned per organization after the API response
                (clamped 1--500). The GraphQL ``name_search`` argument is set when
                ``pipe_name`` is non-empty to reduce payload size server-side.

        Returns:
            dict: A dictionary containing organizations with their pipes.
                  If pipe_name is provided, only pipes matching the name are included,
                  sorted by match score (best matches first).
                  May include ``search_limits`` describing caps applied.

                  When ``pipe_name`` is omitted, per-org ``pipes_truncated`` and
                  ``search_limits.pipes_truncated`` are True when:

                  - the client sliced the list past ``max_pipes_per_org``;
                  - ``pipesCount`` is present and the API returned fewer ``pipes`` than
                    that total; or
                  - ``pipesCount`` is **absent** and the API returned at least
                    ``max_pipes_per_org`` pipes (subset may still be incomplete — conservative hint).
        """
        stripped = pipe_name.strip() if pipe_name else None
        name_search = stripped if stripped else None
        per_org_cap = _clamp_max_pipes_per_org(max_pipes_per_org)
        result = await self.execute_query(
            SEARCH_PIPES_QUERY,
            {"nameSearch": name_search},
        )

        raw_orgs = result.get("organizations", [])
        limits: dict[str, object] = {
            "max_pipes_per_org": per_org_cap,
            "graphql_name_search": name_search is not None,
            "pipes_truncated": False,
        }

        if not stripped:
            organizations: list[dict] = []
            for org in raw_orgs:
                pipes = list(org.get("pipes") or [])
                pipes_count = optional_int(org.get("pipesCount"))
                len_p = len(pipes)
                over_cap = len_p > per_org_cap
                fewer_than_reported_total = (
                    pipes_count is not None and len_p < pipes_count
                )
                at_cap_without_total = (
                    pipes_count is None and len_p >= per_org_cap and len_p > 0
                )
                truncated = (
                    over_cap or fewer_than_reported_total or at_cap_without_total
                )
                if over_cap:
                    pipes = pipes[:per_org_cap]
                row: dict = {
                    "id": org.get("id"),
                    "name": org.get("name"),
                    "pipes": pipes,
                }
                if pipes_count is not None:
                    row["pipesCount"] = pipes_count
                if truncated:
                    row["pipes_truncated"] = True
                    limits["pipes_truncated"] = True
                organizations.append(row)
            return {"organizations": organizations, "search_limits": limits}

        filtered_orgs = []

        for org in raw_orgs:
            matching_pipes = []
            for pipe in org.get("pipes", []):
                pipe_display_name = pipe.get("name", "")
                if stripped.lower() in pipe_display_name.lower():
                    matching_pipes.append((100.0, pipe))
                else:
                    score = fuzz.WRatio(
                        stripped, pipe_display_name, score_cutoff=match_threshold
                    )
                    if score:
                        matching_pipes.append((score, pipe))

            if matching_pipes:
                matching_pipes.sort(key=lambda x: x[0], reverse=True)
                sliced = matching_pipes[:per_org_cap]
                entry: dict = {
                    "id": org.get("id"),
                    "name": org.get("name"),
                    "pipes": [
                        {**pipe, "match_score": round(score, 1)}
                        for score, pipe in sliced
                    ],
                }
                if len(matching_pipes) > per_org_cap:
                    entry["pipes_truncated"] = True
                    limits["pipes_truncated"] = True
                filtered_orgs.append(entry)

        return {"organizations": filtered_orgs, "search_limits": limits}

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

    async def _fetch_phase_cards_count_row(self, phase_id: str | int) -> dict:
        variables = {"phase_id": str(phase_id)}
        result = await self.execute_query(GET_PHASE_CARDS_COUNT_QUERY, variables)
        phase = (result or {}).get("phase")
        if not isinstance(phase, dict) or phase.get("cards_count") is None:
            raise ValueError("phase.cards_count missing from response")
        if phase.get("id") is None:
            raise ValueError("phase id missing from response")
        return phase

    async def get_phase_cards_count(self, phase_id: str | int) -> int:
        """Return the total card count for ``phase_id`` via ``Phase.cards_count``.

        Uses the native schema scalar — no card enumeration, no phase filter
        workaround on ``CardSearch`` (which does not expose one).

        Args:
            phase_id: Phase ID.

        Returns:
            Integer card count as reported by Pipefy.

        Raises:
            ValueError: ``phase.cards_count`` is missing from the response.
        """
        phase = await self._fetch_phase_cards_count_row(phase_id)
        return int(phase["cards_count"])

    async def get_phase_cards_count_payload(self, phase_id: str | int) -> dict:
        """Return phase id, name, and native ``cards_count`` for agent inventory tools."""
        phase = await self._fetch_phase_cards_count_row(phase_id)
        return {
            "phase_id": str(phase["id"]),
            "phase_name": str(phase.get("name") or ""),
            "cards_count": int(phase["cards_count"]),
        }

    async def get_phase_cards(
        self,
        phase_id: str | int,
        *,
        first: int | None = None,
        after: str | None = None,
        include_fields: bool = False,
    ) -> dict:
        """List cards currently in ``phase_id`` via ``Phase.cards`` (Relay pagination).

        Args:
            phase_id: Phase ID.
            first: Max cards per page.
            after: Cursor from ``pageInfo.endCursor``.
            include_fields: When True, include each card's custom fields.

        Returns:
            Raw GraphQL payload (``phase`` key at top level).
        """
        variables: dict[str, Any] = {
            "phase_id": str(phase_id),
            "includeFields": include_fields,
        }
        if first is not None:
            variables["first"] = first
        if after is not None:
            variables["after"] = after
        return await self.execute_query(GET_PHASE_CARDS_QUERY, variables)

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

        if fields:
            fields = parse_field_definitions(fields, action="return phase fields")

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
