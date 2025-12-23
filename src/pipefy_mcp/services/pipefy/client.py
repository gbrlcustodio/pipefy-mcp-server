from __future__ import annotations

from typing import Any

from gql import Client

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.card_service import CardService
from pipefy_mcp.services.pipefy.pipe_service import PipeService
from pipefy_mcp.services.pipefy.types import CardSearch


class PipefyClient:
    """Facade client for Pipefy API operations (pure delegation)."""

    def __init__(self, schema: str | None = None):
        graphql = BasePipefyClient(schema=schema)

        # Keep `client` as a public attribute for backward compatibility.
        self.client: Client = graphql.client

        # Service layer (domain logic lives here).
        self._pipe_service = PipeService(self.client)
        self._card_service = CardService(self.client)

    async def get_pipe(self, pipe_id: int) -> dict:
        return await self._pipe_service.get_pipe(pipe_id)

    async def create_card(self, pipe_id: int, fields: dict) -> dict:
        return await self._card_service.create_card(pipe_id, fields)

    async def get_card(self, card_id: int) -> dict:
        return await self._card_service.get_card(card_id)

    async def get_cards(self, pipe_id: int, search: CardSearch) -> dict:
        return await self._card_service.get_cards(pipe_id, search)

    async def move_card_to_phase(self, card_id: int, destination_phase_id: int) -> dict:
        return await self._card_service.move_card_to_phase(
            card_id, destination_phase_id
        )

    async def update_card_field(
        self, card_id: int, field_id: str, new_value: Any
    ) -> dict:
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
        return await self._card_service.update_card(
            card_id=card_id,
            title=title,
            assignee_ids=assignee_ids,
            label_ids=label_ids,
            due_date=due_date,
            field_updates=field_updates,
        )

    async def get_start_form_fields(
        self, pipe_id: int, required_only: bool = False
    ) -> dict:
        return await self._pipe_service.get_start_form_fields(pipe_id, required_only)
