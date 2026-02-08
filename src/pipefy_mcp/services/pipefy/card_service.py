from __future__ import annotations

from typing import Any

from gql import Client

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.card_queries import (
    CREATE_CARD_MUTATION,
    CREATE_COMMENT_MUTATION,
    DELETE_CARD_MUTATION,
    DELETE_COMMENT_MUTATION,
    FIND_CARDS_QUERY,
    GET_CARD_QUERY,
    GET_CARDS_QUERY,
    MOVE_CARD_TO_PHASE_MUTATION,
    UPDATE_CARD_FIELD_MUTATION,
    UPDATE_CARD_MUTATION,
    UPDATE_COMMENT_MUTATION,
    UPDATE_FIELDS_VALUES_MUTATION,
)
from pipefy_mcp.services.pipefy.types import CardSearch
from pipefy_mcp.services.pipefy.utils.formatters import (
    convert_fields_to_array,
    convert_values_to_camel_case,
)


class CardService(BasePipefyClient):
    """Service for Card-related operations."""

    def __init__(self, client: Client) -> None:
        super().__init__(client=client)

    async def create_card(self, pipe_id: int, fields: dict) -> dict:
        """Create a card in the specified pipe with the given fields."""
        variables = {"pipe_id": pipe_id, "fields": convert_fields_to_array(fields)}
        return await self.execute_query(CREATE_CARD_MUTATION, variables)

    async def create_comment(self, card_id: int, text: str) -> dict:
        """Create a text comment on the specified card."""
        variables = {"input": {"card_id": card_id, "text": text}}
        return await self.execute_query(CREATE_COMMENT_MUTATION, variables)

    async def update_comment(self, comment_id: int, text: str) -> dict:
        """Update an existing comment by its ID."""
        variables = {"input": {"id": comment_id, "text": text}}
        return await self.execute_query(UPDATE_COMMENT_MUTATION, variables)

    async def delete_comment(self, comment_id: int) -> dict:
        """Delete a comment by its ID."""
        variables = {"input": {"id": comment_id}}
        return await self.execute_query(DELETE_COMMENT_MUTATION, variables)

    async def delete_card(self, card_id: int) -> dict:
        """Delete a card by its ID."""
        variables = {"input": {"id": card_id}}
        return await self.execute_query(DELETE_CARD_MUTATION, variables)

    async def get_card(self, card_id: int, include_fields: bool = False) -> dict:
        """Get a card by its ID.

        Args:
            card_id: The ID of the card.
            include_fields: If True, include the card's custom fields (name, value) in the response.
        """
        variables = {"card_id": card_id, "includeFields": include_fields}
        return await self.execute_query(GET_CARD_QUERY, variables)

    async def get_cards(
        self,
        pipe_id: int,
        search: CardSearch | None = None,
        include_fields: bool = False,
    ) -> dict:
        """Get all cards in the pipe.

        Args:
            pipe_id: The ID of the pipe.
            search: Optional search filters.
            include_fields: If True, include each card's custom fields (name, value) in the response.
        """
        variables: dict[str, Any] = {
            "pipe_id": pipe_id,
            "search": {},
            "includeFields": include_fields,
        }
        if search is not None:
            variables["search"] = search
        return await self.execute_query(GET_CARDS_QUERY, variables)

    async def find_cards(
        self,
        pipe_id: int,
        field_id: str,
        field_value: str,
        include_fields: bool = False,
    ) -> dict:
        """Find cards in the pipe where the given field equals the given value.

        Args:
            pipe_id: The ID of the pipe to search in.
            field_id: Pipefy field identifier (e.g. from get_start_form_fields or get_phase_fields).
            field_value: Value to match for that field (string; use format expected by field type).
            include_fields: If True, include each card's custom fields (name, value) in the response.
        """
        variables: dict[str, Any] = {
            "pipeId": pipe_id,
            "search": {"fieldId": field_id, "fieldValue": field_value},
            "includeFields": include_fields,
        }
        return await self.execute_query(FIND_CARDS_QUERY, variables)

    async def move_card_to_phase(self, card_id: int, destination_phase_id: int) -> dict:
        """Move a card to a specific phase.

        Args:
            card_id: The ID of the card to move.
            destination_phase_id: The ID of the destination phase.
        """
        variables = {
            "input": {"card_id": card_id, "destination_phase_id": destination_phase_id}
        }
        return await self.execute_query(MOVE_CARD_TO_PHASE_MUTATION, variables)

    async def update_card_field(
        self, card_id: int, field_id: str, new_value: Any
    ) -> dict:
        """Update a single field of a card.

        Args:
            card_id: The ID of the card containing the field to update.
            field_id: The ID of the field to update.
            new_value: The new value for the field (string, number, list, etc.).

        Returns:
            dict: GraphQL response with success status and updated card information.
        """
        variables = {
            "input": {"card_id": card_id, "field_id": field_id, "new_value": new_value}
        }
        return await self.execute_query(UPDATE_CARD_FIELD_MUTATION, variables)

    async def update_card(
        self,
        card_id: int,
        title: str | None = None,
        assignee_ids: list[int] | None = None,
        label_ids: list[int] | None = None,
        due_date: str | None = None,
        field_updates: list[dict] | None = None,
    ) -> dict:
        """Update a card's fields and attributes with intelligent mutation selection.

        This method automatically chooses between two modes based on parameters:

        **Attribute Mode** (uses `updateCard` mutation):
        For updating card attributes like title, assignees, labels, due_date.

        **Field Mode** (uses `updateFieldsValues` mutation):
        For updating custom fields via field_updates list.

        If field_updates is empty or omitted, only card attributes will be updated.
        """
        if field_updates:
            return await self._execute_update_fields_values(card_id, field_updates)

        return await self._execute_update_card(
            card_id=card_id,
            title=title,
            assignee_ids=assignee_ids,
            label_ids=label_ids,
            due_date=due_date,
        )

    async def _execute_update_card(
        self,
        card_id: int,
        title: str | None,
        assignee_ids: list[int] | None,
        label_ids: list[int] | None,
        due_date: str | None,
    ) -> dict:
        """Execute updateCard mutation for card attributes (title, assignees, labels, due_date)."""
        input_data: dict[str, Any] = {"id": card_id}

        if title is not None:
            input_data["title"] = title
        if assignee_ids is not None:
            input_data["assignee_ids"] = assignee_ids
        if label_ids is not None:
            input_data["label_ids"] = label_ids
        if due_date is not None:
            input_data["due_date"] = due_date

        variables = {"input": input_data}
        return await self.execute_query(UPDATE_CARD_MUTATION, variables)

    async def _execute_update_fields_values(
        self, card_id: int, values: list[dict]
    ) -> dict:
        """Execute updateFieldsValues mutation (incremental mode)."""
        formatted_values = convert_values_to_camel_case(values)
        variables = {"input": {"nodeId": card_id, "values": formatted_values}}
        return await self.execute_query(UPDATE_FIELDS_VALUES_MUTATION, variables)
