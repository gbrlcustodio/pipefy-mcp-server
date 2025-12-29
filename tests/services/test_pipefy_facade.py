from unittest.mock import AsyncMock

import pytest

from pipefy_mcp.services.pipefy.client import PipefyClient


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_facade_delegates_to_services_without_modifying_args_or_return():
    """Test PipefyClient is a pure facade: delegates calls unchanged to services."""
    pipe_service = AsyncMock()
    card_service = AsyncMock()

    pipe_service.get_pipe = AsyncMock(return_value={"ok": "pipe"})
    pipe_service.get_start_form_fields = AsyncMock(return_value={"ok": "fields"})

    card_service.create_card = AsyncMock(return_value={"ok": "create"})
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

    assert await client.get_card(4) == {"ok": "card"}
    card_service.get_card.assert_awaited_once_with(4)

    assert await client.get_cards(5, {"title": "x"}) == {"ok": "cards"}
    card_service.get_cards.assert_awaited_once_with(5, {"title": "x"})

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
def test_pipefy_client_injects_same_shared_client_instance_into_services():
    """Test PipefyClient creates one shared gql.Client and injects it into both services."""
    from unittest.mock import MagicMock, patch

    from gql import Client

    # Mock the BasePipefyClient._create_client to avoid OAuth dependencies
    mock_client_instance = MagicMock(spec=Client)

    with patch(
        "pipefy_mcp.services.pipefy.base_client.BasePipefyClient._create_client",
        return_value=mock_client_instance,
    ):
        # Create a real PipefyClient (it will use the mocked _create_client)
        client = PipefyClient()

    # Verify that both services received the same client instance
    assert client._pipe_service.client is client._card_service.client
    # Verify that the shared client is also exposed as the public `client` attribute
    assert client.client is client._pipe_service.client
    assert client.client is client._card_service.client
    # Verify it's the same mock instance we injected
    assert client.client is mock_client_instance
