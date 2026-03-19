from unittest.mock import AsyncMock, MagicMock

import pytest

from pipefy_mcp.services.pipefy.card_service import CardService
from pipefy_mcp.services.pipefy.client import PipefyClient
from pipefy_mcp.services.pipefy.pipe_config_service import PipeConfigService
from pipefy_mcp.services.pipefy.pipe_service import PipeService
from pipefy_mcp.services.pipefy.schema_introspection_service import (
    SchemaIntrospectionService,
)
from pipefy_mcp.settings import PipefySettings


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_facade_delegates_to_services_without_modifying_args_or_return():
    """Test PipefyClient is a pure facade: delegates calls unchanged to services."""
    pipe_service = AsyncMock()
    card_service = AsyncMock()
    pipe_config_service = AsyncMock()

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

    pipe_config_service.create_pipe = AsyncMock(return_value={"ok": "create_pipe"})
    pipe_config_service.update_pipe = AsyncMock(return_value={"ok": "update_pipe"})
    pipe_config_service.delete_pipe = AsyncMock(return_value={"ok": "delete_pipe"})
    pipe_config_service.clone_pipe = AsyncMock(return_value={"ok": "clone_pipe"})
    pipe_config_service.create_phase = AsyncMock(return_value={"ok": "create_phase"})
    pipe_config_service.update_phase = AsyncMock(return_value={"ok": "update_phase"})
    pipe_config_service.delete_phase = AsyncMock(return_value={"ok": "delete_phase"})
    pipe_config_service.create_phase_field = AsyncMock(
        return_value={"ok": "create_phase_field"}
    )
    pipe_config_service.update_phase_field = AsyncMock(
        return_value={"ok": "update_phase_field"}
    )
    pipe_config_service.delete_phase_field = AsyncMock(
        return_value={"ok": "delete_phase_field"}
    )
    pipe_config_service.create_label = AsyncMock(return_value={"ok": "create_label"})
    pipe_config_service.update_label = AsyncMock(return_value={"ok": "update_label"})
    pipe_config_service.delete_label = AsyncMock(return_value={"ok": "delete_label"})

    client = PipefyClient.__new__(PipefyClient)
    client._pipe_service = pipe_service
    client._card_service = card_service
    client._pipe_config_service = pipe_config_service

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

    assert await client.create_pipe("P", 100) == {"ok": "create_pipe"}
    pipe_config_service.create_pipe.assert_awaited_once_with("P", 100)

    assert await client.update_pipe(200, name="N") == {"ok": "update_pipe"}
    pipe_config_service.update_pipe.assert_awaited_once_with(200, name="N")

    assert await client.delete_pipe(300) == {"ok": "delete_pipe"}
    pipe_config_service.delete_pipe.assert_awaited_once_with(300)

    assert await client.clone_pipe(400, organization_id=500) == {"ok": "clone_pipe"}
    pipe_config_service.clone_pipe.assert_awaited_once_with(400, organization_id=500)

    assert await client.create_phase(1, "P1", done=True, index=2.0) == {
        "ok": "create_phase"
    }
    pipe_config_service.create_phase.assert_awaited_once_with(
        1, "P1", done=True, index=2.0, description=None
    )

    assert await client.update_phase(9, name="N") == {"ok": "update_phase"}
    pipe_config_service.update_phase.assert_awaited_once_with(9, name="N")

    assert await client.delete_phase(8) == {"ok": "delete_phase"}
    pipe_config_service.delete_phase.assert_awaited_once_with(8)

    assert await client.create_phase_field(
        11,
        "Title",
        "short_text",
        required=True,
    ) == {"ok": "create_phase_field"}
    pipe_config_service.create_phase_field.assert_awaited_once_with(
        11,
        "Title",
        "short_text",
        required=True,
    )

    assert await client.update_phase_field(12, label="L") == {
        "ok": "update_phase_field"
    }
    pipe_config_service.update_phase_field.assert_awaited_once_with(12, label="L")

    assert await client.delete_phase_field(13) == {"ok": "delete_phase_field"}
    pipe_config_service.delete_phase_field.assert_awaited_once_with(13)

    assert await client.create_label(14, "Bug", "red") == {"ok": "create_label"}
    pipe_config_service.create_label.assert_awaited_once_with(14, "Bug", "red")

    assert await client.update_label(15, name="Story") == {"ok": "update_label"}
    pipe_config_service.update_label.assert_awaited_once_with(15, name="Story")

    assert await client.delete_label(16) == {"ok": "delete_label"}
    pipe_config_service.delete_label.assert_awaited_once_with(16)


@pytest.mark.unit
def test_pipefy_client_creates_services_with_shared_auth():
    """Test PipefyClient creates services that share the same OAuth auth instance."""

    settings = PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )
    client = PipefyClient(settings=settings)

    assert isinstance(client._pipe_service, PipeService)
    assert isinstance(client._card_service, CardService)
    assert isinstance(client._pipe_config_service, PipeConfigService)
    assert isinstance(client._introspection_service, SchemaIntrospectionService)
    assert client._pipe_service._auth is not None, (
        "PipeService should have an auth instance"
    )
    assert client._card_service._auth is not None, (
        "CardService should have an auth instance"
    )
    assert client._introspection_service._auth is not None, (
        "SchemaIntrospectionService should have an auth instance"
    )
    assert client._pipe_config_service._auth is not None, (
        "PipeConfigService should have an auth instance"
    )
    assert client._pipe_service._auth is client._card_service._auth
    assert client._pipe_service._auth is client._pipe_config_service._auth
    assert client._pipe_service._auth is client._introspection_service._auth


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_introspection_methods_delegate_to_introspection_service():
    """Facade forwards introspection and raw GraphQL calls unchanged."""
    intro = AsyncMock()
    intro.introspect_type = AsyncMock(return_value={"name": "T"})
    intro.introspect_mutation = AsyncMock(return_value={"name": "m"})
    intro.search_schema = AsyncMock(return_value={"types": []})
    intro.execute_graphql = AsyncMock(return_value={"data": True})

    client = PipefyClient.__new__(PipefyClient)
    client._pipe_service = MagicMock()
    client._card_service = MagicMock()
    client._pipe_config_service = MagicMock()
    client._introspection_service = intro

    assert await client.introspect_type("Card") == {"name": "T"}
    intro.introspect_type.assert_awaited_once_with("Card")

    assert await client.introspect_mutation("createCard") == {"name": "m"}
    intro.introspect_mutation.assert_awaited_once_with("createCard")

    assert await client.search_schema("pipe") == {"types": []}
    intro.search_schema.assert_awaited_once_with("pipe")

    assert await client.execute_graphql("query { x }", {"a": 1}) == {"data": True}
    intro.execute_graphql.assert_awaited_once_with("query { x }", {"a": 1})

    intro.execute_graphql.reset_mock()
    intro.execute_graphql.return_value = {"ok": 2}
    assert await client.execute_graphql("query { y }", None) == {"ok": 2}
    intro.execute_graphql.assert_awaited_once_with("query { y }", None)
