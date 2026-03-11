from unittest.mock import AsyncMock

import pytest

from pipefy_mcp.services.pipefy.client import PipefyClient
from pipefy_mcp.settings import PipefySettings


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_facade_delegates_to_services_without_modifying_args_or_return():
    """Test PipefyClient is a pure facade: delegates calls unchanged to services."""
    pipe_service = AsyncMock()
    card_service = AsyncMock()

    pipe_service.get_pipe = AsyncMock(return_value={"ok": "pipe"})
    pipe_service.get_start_form_fields = AsyncMock(return_value={"ok": "fields"})

    card_service.create_card = AsyncMock(return_value={"ok": "create"})
    card_service.create_comment = AsyncMock(return_value={"ok": "comment"})
    card_service.delete_card = AsyncMock(return_value={"ok": "delete"})
    card_service.get_card = AsyncMock(return_value={"ok": "card"})
    card_service.get_cards = AsyncMock(return_value={"ok": "cards"})
    card_service.move_card_to_phase = AsyncMock(return_value={"ok": "move"})
    card_service.update_card_field = AsyncMock(return_value={"ok": "update_field"})
    card_service.update_card = AsyncMock(return_value={"ok": "update_card"})

    client = PipefyClient.__new__(PipefyClient)
    client._pipe_service = pipe_service
    client._card_service = card_service

    assert await client.get_pipe(1) == {"ok": "pipe"}
    pipe_service.get_pipe.assert_awaited_once_with(1)

    assert await client.get_start_form_fields(2, True) == {"ok": "fields"}
    pipe_service.get_start_form_fields.assert_awaited_once_with(2, True)

    assert await client.create_card(3, {"a": 1}) == {"ok": "create"}
    card_service.create_card.assert_awaited_once_with(3, {"a": 1})

    assert await client.add_card_comment(33, "hello") == {"ok": "comment"}
    card_service.create_comment.assert_awaited_once_with(33, "hello")

    assert await client.delete_card(34) == {"ok": "delete"}
    card_service.delete_card.assert_awaited_once_with(34)

    assert await client.get_card(4) == {"ok": "card"}
    card_service.get_card.assert_awaited_once_with(4, include_fields=False)

    assert await client.get_cards(5, {"title": "x"}) == {"ok": "cards"}
    card_service.get_cards.assert_awaited_once_with(
        5, {"title": "x"}, include_fields=False
    )

    assert await client.move_card_to_phase(6, 7) == {"ok": "move"}
    card_service.move_card_to_phase.assert_awaited_once_with(6, 7)

    assert await client.update_card_field(8, "f", 123) == {"ok": "update_field"}
    card_service.update_card_field.assert_awaited_once_with(8, "f", 123)

    assert await client.update_card(
        card_id=9,
        title="t",
        assignee_ids=[1, 2],
        label_ids=[3],
        due_date="2025-01-01",
        field_updates=[{"field_id": "x", "value": "y"}],
    ) == {"ok": "update_card"}
    card_service.update_card.assert_awaited_once_with(
        card_id=9,
        title="t",
        assignee_ids=[1, 2],
        label_ids=[3],
        due_date="2025-01-01",
        field_updates=[{"field_id": "x", "value": "y"}],
    )


@pytest.mark.unit
def test_pipefy_client_creates_services_with_shared_auth():
    """Test PipefyClient creates services that share the same OAuth auth instance."""
    from pipefy_mcp.services.pipefy.card_service import CardService
    from pipefy_mcp.services.pipefy.pipe_service import PipeService

    settings = PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )
    client = PipefyClient(settings=settings)

    assert isinstance(client._pipe_service, PipeService)
    assert isinstance(client._card_service, CardService)
    # Each service holds its own auth instance that reuses the token cache
    assert client._pipe_service._auth is not None
    assert client._card_service._auth is not None
