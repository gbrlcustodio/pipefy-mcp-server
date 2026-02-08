from __future__ import annotations

from typing import Any

from gql import Client

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.card_service import CardService
from pipefy_mcp.services.pipefy.pipe_service import PipeService
from pipefy_mcp.services.pipefy.types import CardSearch
from pipefy_mcp.settings import PipefySettings


class PipefyClient:
    """Facade client for Pipefy API operations (pure delegation)."""

    def __init__(self, settings: PipefySettings, schema: str | None = None):
        graphql = BasePipefyClient(settings=settings, schema=schema)

        # Keep `client` as a public attribute for backward compatibility.
        self.client: Client = graphql.client

        # Service layer (domain logic lives here).
        self._pipe_service = PipeService(self.client)
        self._card_service = CardService(self.client)

    async def get_pipe(self, pipe_id: int) -> dict:
        """Get a pipe by ID, including phases, labels, and start form fields."""
        return await self._pipe_service.get_pipe(pipe_id)

    async def get_pipe_members(self, pipe_id: int) -> dict:
        """Get the members of a pipe."""
        return await self._pipe_service.get_pipe_members(pipe_id)

    async def create_card(self, pipe_id: int, fields: dict) -> dict:
        """Create a card in the specified pipe with the given fields."""
        return await self._card_service.create_card(pipe_id, fields)

    async def add_card_comment(self, card_id: int, text: str) -> dict:
        """Add a text comment to a card by its ID."""
        return await self._card_service.create_comment(card_id, text)

    async def update_comment(self, comment_id: int, text: str) -> dict:
        """Update an existing comment by its ID."""
        return await self._card_service.update_comment(comment_id, text)

    async def delete_comment(self, comment_id: int) -> dict:
        """Delete a comment by its ID."""
        return await self._card_service.delete_comment(comment_id)

    async def get_card(self, card_id: int, include_fields: bool = False) -> dict:
        """Get a card by its ID.

        Args:
            card_id: The ID of the card.
            include_fields: If True, include the card's custom fields (name, value) in the response.
        """
        return await self._card_service.get_card(card_id, include_fields=include_fields)

    async def get_cards(
        self,
        pipe_id: int,
        search: CardSearch | None = None,
        include_fields: bool = False,
    ) -> dict:
        """Get all cards in the pipe with optional search filters.

        Args:
            pipe_id: The ID of the pipe.
            search: Optional search filters.
            include_fields: If True, include each card's custom fields (name, value) in the response.
        """
        return await self._card_service.get_cards(
            pipe_id, search, include_fields=include_fields
        )

    async def move_card_to_phase(self, card_id: int, destination_phase_id: int) -> dict:
        """Move a card to a specific phase."""
        return await self._card_service.move_card_to_phase(
            card_id, destination_phase_id
        )

    async def update_card_field(
        self, card_id: int, field_id: str, new_value: Any
    ) -> dict:
        """Update a single field of a card."""
        return await self._card_service.update_card_field(card_id, field_id, new_value)

    async def update_card(
        self,
        card_id: int,
        title: str | None = None,
        assignee_ids: list[int] | None = None,
        label_ids: list[int] | None = None,
        due_date: str | None = None,
        field_updates: list[dict] | None = None,
    ) -> dict:
        """Update a card's attributes or fields with intelligent mutation selection."""
        return await self._card_service.update_card(
            card_id=card_id,
            title=title,
            assignee_ids=assignee_ids,
            label_ids=label_ids,
            due_date=due_date,
            field_updates=field_updates,
        )

    async def delete_card(self, card_id: int) -> dict:
        """Delete a card by its ID."""
        return await self._card_service.delete_card(card_id)

    async def get_start_form_fields(
        self, pipe_id: int, required_only: bool = False
    ) -> dict:
        """Get the start form fields of a pipe."""
        return await self._pipe_service.get_start_form_fields(pipe_id, required_only)

    async def search_pipes(self, pipe_name: str | None = None) -> dict:
        """Search for pipes across all organizations"""
        return await self._pipe_service.search_pipes(pipe_name)

    async def get_phase_fields(
        self, phase_id: int, required_only: bool = False
    ) -> dict:
        """Get the fields available in a specific phase."""
        return await self._pipe_service.get_phase_fields(phase_id, required_only)
