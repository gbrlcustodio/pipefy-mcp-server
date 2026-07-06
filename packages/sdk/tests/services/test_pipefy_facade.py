from unittest.mock import AsyncMock, MagicMock

import pytest
from pipefy_auth import StaticBearerAuth

from pipefy_sdk import __version__
from pipefy_sdk.client import PipefyClient, build_executors
from pipefy_sdk.services.ai_agent_service import AiAgentService
from pipefy_sdk.services.attachment_service import AttachmentService
from pipefy_sdk.services.automation_service import AutomationService
from pipefy_sdk.services.card_service import CardService
from pipefy_sdk.services.member_service import MemberService
from pipefy_sdk.services.pipe_config_service import PipeConfigService
from pipefy_sdk.services.pipe_service import PipeService
from pipefy_sdk.services.relation_service import RelationService
from pipefy_sdk.services.schema_introspection_service import (
    SchemaIntrospectionService,
)
from pipefy_sdk.services.table_service import TableService
from pipefy_sdk.services.webhook_service import WebhookService
from pipefy_sdk.settings import PipefySettings
from pipefy_sdk.telemetry import telemetry_headers


@pytest.fixture
def mock_settings():
    return PipefySettings(
        base_url="https://api.pipefy.com",
    )


@pytest.mark.unit
def test_pipefy_client_forwards_caller_provided_auth(mock_settings):
    auth = StaticBearerAuth("unit-token")
    client = PipefyClient(mock_settings, auth=auth)
    # Public services share one executor bound to the caller's auth, so GraphQL
    # auth cannot drift across services.
    assert client._card_service._executor.auth is auth
    assert client._pipe_service._executor.auth is auth
    assert client._internal_executor.auth is auth


@pytest.mark.unit
def test_build_executors_routes_each_endpoint_to_its_url(mock_settings):
    ex = build_executors(mock_settings, StaticBearerAuth("unit-token"))
    # Each executor must target its own endpoint; a copy-paste that aimed
    # interfaces or internal at the public graphql_url would route silently.
    assert ex.public.endpoint._graphql_url == mock_settings.graphql_url
    assert ex.interfaces.endpoint._graphql_url == mock_settings.interfaces_graphql_url
    assert ex.internal.endpoint._graphql_url == mock_settings.internal_api_url


@pytest.mark.unit
def test_build_executors_stamps_each_endpoint_with_telemetry_headers():
    settings = PipefySettings(base_url="https://api.pipefy.com")
    ex = build_executors(settings, StaticBearerAuth("unit-token"), surface="mcp")
    expected = telemetry_headers(surface="mcp", version=__version__)
    assert ex.public.endpoint._headers == expected
    assert ex.interfaces.endpoint._headers == expected
    assert ex.internal.endpoint._headers == expected


@pytest.mark.unit
def test_build_executors_defaults_surface_to_sdk():
    """Direct SDK use passes no surface, so the endpoints stamp the 'sdk' default."""
    ex = build_executors(
        PipefySettings(base_url="https://api.pipefy.com"),
        StaticBearerAuth("unit-token"),
    )
    expected = telemetry_headers(surface="sdk", version=__version__)
    assert ex.public.endpoint._headers == expected
    assert ex.interfaces.endpoint._headers == expected
    assert ex.internal.endpoint._headers == expected


@pytest.mark.unit
def test_pipefy_client_threads_surface_to_endpoints():
    """The surface passed to the facade reaches the endpoints it builds."""
    client = PipefyClient(
        PipefySettings(base_url="https://api.pipefy.com"),
        auth=StaticBearerAuth("unit-token"),
        surface="cli",
    )
    assert client._internal_executor.endpoint._headers == telemetry_headers(
        surface="cli", version=__version__
    )


@pytest.mark.unit
def test_env_var_cannot_forge_surface(monkeypatch: pytest.MonkeyPatch):
    """``PIPEFY_CLIENT_SURFACE`` cannot forge the surface.

    The surface is a constructor argument, not a setting, so it is never read
    from the environment: a default client stamps 'sdk' regardless of the env var.
    """
    monkeypatch.setenv("PIPEFY_CLIENT_SURFACE", "mcp")
    client = PipefyClient(
        PipefySettings(base_url="https://api.pipefy.com"),
        auth=StaticBearerAuth("unit-token"),
    )
    assert client._internal_executor.endpoint._headers == telemetry_headers(
        surface="sdk", version=__version__
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_card_forwards_phase_id_and_title(mock_settings):
    """PipefyClient.create_card passes optional phase_id and title to CardService."""
    card_service = AsyncMock()
    card_service.create_card = AsyncMock(return_value={"ok": "create"})
    client = PipefyClient(mock_settings, auth=StaticBearerAuth("unit-token"))
    client._card_service = card_service

    await client.create_card(10, {}, phase_id=20, title="Seed")

    card_service.create_card.assert_awaited_once_with(10, {}, phase_id=20, title="Seed")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_facade_delegates_to_services_without_modifying_args_or_return():
    """Test PipefyClient is a pure facade: delegates calls unchanged to services."""
    pipe_service = AsyncMock()
    card_service = AsyncMock()
    pipe_config_service = AsyncMock()
    table_service = AsyncMock()

    pipe_service.get_pipe = AsyncMock(return_value={"ok": "pipe"})
    pipe_service.get_pipe_with_preferences = AsyncMock(
        return_value={"ok": "pipe_prefs"}
    )
    pipe_service.get_start_form_fields = AsyncMock(return_value={"ok": "fields"})

    card_service.create_card = AsyncMock(return_value={"ok": "create"})
    card_service.create_comment = AsyncMock(return_value={"ok": "comment"})
    card_service.delete_card = AsyncMock(return_value={"ok": "delete"})
    card_service.get_card_relations = AsyncMock(return_value={"ok": "card_relations"})
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
    pipe_config_service.create_field_condition = AsyncMock(
        return_value={"ok": "create_field_condition"}
    )
    pipe_config_service.update_field_condition = AsyncMock(
        return_value={"ok": "update_field_condition"}
    )
    pipe_config_service.delete_field_condition = AsyncMock(
        return_value={"ok": "delete_field_condition"}
    )
    pipe_config_service.get_field_conditions = AsyncMock(
        return_value={"ok": "get_field_conditions"}
    )
    pipe_config_service.get_field_condition = AsyncMock(
        return_value={"ok": "get_field_condition"}
    )

    table_service.get_table = AsyncMock(return_value={"ok": "get_table"})
    table_service.get_tables = AsyncMock(return_value={"ok": "get_tables"})
    table_service.get_table_records = AsyncMock(
        return_value={"ok": "get_table_records"}
    )
    table_service.get_table_record = AsyncMock(return_value={"ok": "get_table_record"})
    table_service.find_records = AsyncMock(return_value={"ok": "find_records"})
    table_service.create_table = AsyncMock(return_value={"ok": "create_table"})
    table_service.update_table = AsyncMock(return_value={"ok": "update_table"})
    table_service.delete_table = AsyncMock(return_value={"ok": "delete_table"})
    table_service.create_table_record = AsyncMock(
        return_value={"ok": "create_table_record"}
    )
    table_service.update_table_record = AsyncMock(
        return_value={"ok": "update_table_record"}
    )
    table_service.delete_table_record = AsyncMock(
        return_value={"ok": "delete_table_record"}
    )
    table_service.set_table_record_field_value = AsyncMock(
        return_value={"ok": "set_table_record_field_value"}
    )
    table_service.create_table_field = AsyncMock(
        return_value={"ok": "create_table_field"}
    )
    table_service.update_table_field = AsyncMock(
        return_value={"ok": "update_table_field"}
    )
    table_service.delete_table_field = AsyncMock(
        return_value={"ok": "delete_table_field"}
    )

    relation_service = AsyncMock()
    relation_service.get_pipe_relations = AsyncMock(
        return_value={"ok": "get_pipe_relations"}
    )
    relation_service.get_table_relations = AsyncMock(
        return_value={"ok": "get_table_relations"}
    )
    relation_service.create_pipe_relation = AsyncMock(
        return_value={"ok": "create_pipe_relation"}
    )
    relation_service.update_pipe_relation = AsyncMock(
        return_value={"ok": "update_pipe_relation"}
    )
    relation_service.delete_pipe_relation = AsyncMock(
        return_value={"ok": "delete_pipe_relation"}
    )
    relation_service.create_card_relation = AsyncMock(
        return_value={"ok": "create_card_relation"}
    )

    automation_service = AsyncMock()
    automation_service.get_automation = AsyncMock(return_value={"ok": "get_automation"})
    automation_service.get_automations = AsyncMock(
        return_value={"ok": "get_automations"}
    )
    automation_service.get_automation_actions = AsyncMock(
        return_value={"ok": "get_automation_actions"}
    )
    automation_service.get_automation_events = AsyncMock(
        return_value={"ok": "get_automation_events"}
    )
    automation_service.get_automation_event_attributes = AsyncMock(
        return_value={"ok": "get_automation_event_attributes"}
    )
    automation_service.create_automation = AsyncMock(
        return_value={"ok": "create_automation"}
    )
    automation_service.create_send_task_automation = AsyncMock(
        return_value={"ok": "create_send_task_automation"}
    )
    automation_service.update_automation = AsyncMock(
        return_value={"ok": "update_automation"}
    )
    automation_service.simulate_automation = AsyncMock(
        return_value={"ok": "simulate_automation"}
    )
    automation_service.delete_automation = AsyncMock(
        return_value={"ok": "delete_automation"}
    )

    webhook_service = AsyncMock()
    webhook_service.get_webhooks = AsyncMock(return_value={"ok": "get_webhooks"})
    webhook_service.update_webhook = AsyncMock(return_value={"ok": "update_webhook"})

    ai_agent_service = AsyncMock()
    ai_agent_service.get_agent = AsyncMock(return_value={"ok": "get_ai_agent"})
    ai_agent_service.get_agents = AsyncMock(return_value=[{"uuid": "u1"}])
    ai_agent_service.delete_agent = AsyncMock(return_value={"success": True})

    client = PipefyClient.__new__(PipefyClient)
    client._pipe_service = pipe_service
    client._card_service = card_service
    client._pipe_config_service = pipe_config_service
    client._table_service = table_service
    client._relation_service = relation_service
    client._webhook_service = webhook_service
    client._automation_service = automation_service
    client._ai_agent_service = ai_agent_service

    assert await client.get_pipe(1) == {"ok": "pipe"}
    pipe_service.get_pipe.assert_awaited_once_with(1)

    assert await client.get_pipe_with_preferences(1) == {"ok": "pipe_prefs"}
    pipe_service.get_pipe_with_preferences.assert_awaited_once_with(1)

    assert await client.get_start_form_fields(2, True) == {"ok": "fields"}
    pipe_service.get_start_form_fields.assert_awaited_once_with(2, True)

    assert await client.create_card(3, {"a": 1}) == {"ok": "create"}
    card_service.create_card.assert_awaited_once_with(
        3, {"a": 1}, phase_id=None, title=None
    )

    assert await client.add_card_comment(33, "hello") == {"ok": "comment"}
    card_service.create_comment.assert_awaited_once_with(33, "hello")

    assert await client.delete_card(34) == {"ok": "delete"}
    card_service.delete_card.assert_awaited_once_with(34)

    assert await client.get_card_relations("cr-1") == {"ok": "card_relations"}
    card_service.get_card_relations.assert_awaited_once_with("cr-1")

    assert await client.get_webhooks("p99") == {"ok": "get_webhooks"}
    webhook_service.get_webhooks.assert_awaited_once_with("p99")

    assert await client.update_webhook("w1", name="X") == {"ok": "update_webhook"}
    webhook_service.update_webhook.assert_awaited_once_with("w1", name="X")

    # delete_card_relation routes through the internal GraphQL executor (not CardService),
    # tested separately below.

    assert await client.get_card(4) == {"ok": "card"}
    card_service.get_card.assert_awaited_once_with(4, include_fields=False)

    assert await client.get_cards(5, {"title": "x"}) == {"ok": "cards"}
    card_service.get_cards.assert_awaited_once_with(
        5, {"title": "x"}, include_fields=False, first=None, after=None
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
    pipe_config_service.delete_phase_field.assert_awaited_once_with(13, pipe_uuid=None)

    assert await client.create_label(14, "Bug", "red") == {"ok": "create_label"}
    pipe_config_service.create_label.assert_awaited_once_with(14, "Bug", "red")

    assert await client.update_label(15, name="Story") == {"ok": "update_label"}
    pipe_config_service.update_label.assert_awaited_once_with(15, name="Story")

    assert await client.delete_label(16) == {"ok": "delete_label"}
    pipe_config_service.delete_label.assert_awaited_once_with(16)

    expr = {"expressions": [], "expressions_structure": []}
    acts = [{"phaseFieldId": "pf-target"}]
    assert await client.create_field_condition(
        "pf-1",
        expr,
        acts,
        name="R1",
    ) == {"ok": "create_field_condition"}
    pipe_config_service.create_field_condition.assert_awaited_once_with(
        "pf-1",
        expr,
        acts,
        name="R1",
    )

    assert await client.update_field_condition("c1", name="N") == {
        "ok": "update_field_condition"
    }
    pipe_config_service.update_field_condition.assert_awaited_once_with(
        "c1",
        name="N",
    )

    assert await client.delete_field_condition("c2") == {"ok": "delete_field_condition"}
    pipe_config_service.delete_field_condition.assert_awaited_once_with("c2")

    assert await client.get_field_conditions("ph-3") == {"ok": "get_field_conditions"}
    pipe_config_service.get_field_conditions.assert_awaited_once_with("ph-3")

    assert await client.get_field_condition("fc-1") == {"ok": "get_field_condition"}
    pipe_config_service.get_field_condition.assert_awaited_once_with("fc-1")

    assert await client.get_table("t1") == {"ok": "get_table"}
    table_service.get_table.assert_awaited_once_with("t1")

    assert await client.get_tables([1, 2]) == {"ok": "get_tables"}
    table_service.get_tables.assert_awaited_once_with([1, 2])

    assert await client.get_table_records(9, first=20, after="c") == {
        "ok": "get_table_records"
    }
    table_service.get_table_records.assert_awaited_once_with(9, first=20, after="c")

    assert await client.get_table_record("r") == {"ok": "get_table_record"}
    table_service.get_table_record.assert_awaited_once_with("r")

    assert await client.find_records(1, "f", "v", first=10) == {"ok": "find_records"}
    table_service.find_records.assert_awaited_once_with(
        1, "f", "v", first=10, after=None
    )

    assert await client.create_table("N", 7, description="D") == {"ok": "create_table"}
    table_service.create_table.assert_awaited_once_with("N", 7, description="D")

    assert await client.update_table("tid", name="X") == {"ok": "update_table"}
    table_service.update_table.assert_awaited_once_with("tid", name="X")

    assert await client.delete_table(99) == {"ok": "delete_table"}
    table_service.delete_table.assert_awaited_once_with(99)

    assert await client.create_table_record(3, {"a": "b"}, title="T") == {
        "ok": "create_table_record"
    }
    table_service.create_table_record.assert_awaited_once_with(3, {"a": "b"}, title="T")

    assert await client.update_table_record("r1", {"title": "Z"}) == {
        "ok": "update_table_record"
    }
    table_service.update_table_record.assert_awaited_once_with("r1", {"title": "Z"})

    assert await client.delete_table_record(55) == {"ok": "delete_table_record"}
    table_service.delete_table_record.assert_awaited_once_with(55)

    assert await client.set_table_record_field_value(1, "f", "v") == {
        "ok": "set_table_record_field_value"
    }
    table_service.set_table_record_field_value.assert_awaited_once_with(1, "f", "v")

    assert await client.create_table_field("t", "Lab", "short_text", required=True) == {
        "ok": "create_table_field"
    }
    table_service.create_table_field.assert_awaited_once_with(
        "t", "Lab", "short_text", required=True
    )

    assert await client.update_table_field("fid", label="X") == {
        "ok": "update_table_field"
    }
    table_service.update_table_field.assert_awaited_once_with(
        "fid", table_id=None, label="X"
    )

    assert await client.delete_table_field(9, "tbl_1") == {"ok": "delete_table_field"}
    table_service.delete_table_field.assert_awaited_once_with(9, "tbl_1")

    assert await client.get_pipe_relations(42) == {"ok": "get_pipe_relations"}
    relation_service.get_pipe_relations.assert_awaited_once_with(42)

    assert await client.get_table_relations(["tr1", "tr2"]) == {
        "ok": "get_table_relations"
    }
    relation_service.get_table_relations.assert_awaited_once_with(["tr1", "tr2"])

    assert await client.create_pipe_relation(1, 2, "R") == {
        "ok": "create_pipe_relation"
    }
    relation_service.create_pipe_relation.assert_awaited_once_with(1, 2, "R")

    assert await client.create_pipe_relation(
        1, 2, "R", extra_input={"canCreateNewItems": False}
    ) == {"ok": "create_pipe_relation"}
    relation_service.create_pipe_relation.assert_awaited_with(
        1, 2, "R", canCreateNewItems=False
    )

    assert await client.update_pipe_relation(9, "N") == {"ok": "update_pipe_relation"}
    relation_service.update_pipe_relation.assert_awaited_once_with(9, "N")

    assert await client.update_pipe_relation(
        9, "N", extra_input={"canConnectExistingItems": False}
    ) == {"ok": "update_pipe_relation"}
    relation_service.update_pipe_relation.assert_awaited_with(
        9, "N", canConnectExistingItems=False
    )

    assert await client.delete_pipe_relation(3) == {"ok": "delete_pipe_relation"}
    relation_service.delete_pipe_relation.assert_awaited_once_with(3)

    assert await client.create_card_relation(5, 6, 7) == {"ok": "create_card_relation"}
    relation_service.create_card_relation.assert_awaited_with(5, 6, 7)

    assert await client.create_card_relation(
        1, 2, 3, extra_input={"sourceType": "Field"}
    ) == {"ok": "create_card_relation"}
    relation_service.create_card_relation.assert_awaited_with(
        1, 2, 3, sourceType="Field"
    )

    assert await client.get_automation("aid") == {"ok": "get_automation"}
    automation_service.get_automation.assert_awaited_once_with("aid")

    assert await client.get_automations(pipe_id="pid") == {"ok": "get_automations"}
    automation_service.get_automations.assert_awaited_once_with(
        organization_id=None, pipe_id="pid"
    )

    assert await client.get_automation_actions("p1") == {"ok": "get_automation_actions"}
    automation_service.get_automation_actions.assert_awaited_once_with("p1")

    assert await client.get_automation_events("p2") == {"ok": "get_automation_events"}
    automation_service.get_automation_events.assert_awaited_once_with("p2")

    assert await client.get_automation_event_attributes() == {
        "ok": "get_automation_event_attributes"
    }
    automation_service.get_automation_event_attributes.assert_awaited_once_with()

    assert await client.create_automation("p1", "Rule", "ev", "act") == {
        "ok": "create_automation"
    }
    automation_service.create_automation.assert_awaited_once_with(
        "p1", "Rule", "ev", "act", action_repo_id=None, active=True
    )

    assert await client.create_automation(
        "p1", "Rule", "ev", "act", extra_input={"customKey": "v"}
    ) == {"ok": "create_automation"}
    automation_service.create_automation.assert_awaited_with(
        "p1", "Rule", "ev", "act", action_repo_id=None, active=True, customKey="v"
    )

    assert await client.create_automation("p1", "Rule", "ev", "act", active=False) == {
        "ok": "create_automation"
    }
    automation_service.create_automation.assert_awaited_with(
        "p1", "Rule", "ev", "act", action_repo_id=None, active=False
    )

    assert await client.create_automation(
        "p1", "Rule", "ev", "act", action_repo_id="child-pipe"
    ) == {"ok": "create_automation"}
    automation_service.create_automation.assert_awaited_with(
        "p1", "Rule", "ev", "act", action_repo_id="child-pipe", active=True
    )

    assert await client.create_send_task_automation(
        "p1", "Rule", "card_created", "T", "x@y.com"
    ) == {"ok": "create_send_task_automation"}
    automation_service.create_send_task_automation.assert_awaited_once_with(
        "p1",
        "Rule",
        "card_created",
        "T",
        "x@y.com",
        active=True,
        event_params=None,
        condition=None,
    )

    assert await client.update_automation("a1", extra_input={"name": "N"}) == {
        "ok": "update_automation"
    }
    automation_service.update_automation.assert_awaited_once_with("a1", name="N")

    assert await client.simulate_automation(
        pipe_id="pipe-z",
        action_id="generate_with_ai",
        sample_card_id="c1",
        event_id="card_created",
    ) == {"ok": "simulate_automation"}
    automation_service.simulate_automation.assert_awaited_once_with(
        pipe_id="pipe-z",
        action_id="generate_with_ai",
        sample_card_id="c1",
        event_id="card_created",
        event_params=None,
        action_params=None,
        condition=None,
        name=None,
        extra_input=None,
    )

    assert await client.delete_automation("rm") == {"ok": "delete_automation"}
    automation_service.delete_automation.assert_awaited_once_with("rm")

    assert await client.get_ai_agent("au-1") == {"ok": "get_ai_agent"}
    ai_agent_service.get_agent.assert_awaited_once_with("au-1")

    assert await client.get_ai_agents("repo-9") == [{"uuid": "u1"}]
    ai_agent_service.get_agents.assert_awaited_once_with("repo-9")

    assert await client.delete_ai_agent("del-1") == {"success": True}
    ai_agent_service.delete_agent.assert_awaited_once_with("del-1")


@pytest.mark.unit
def test_pipefy_client_creates_services_with_shared_auth():
    """Test PipefyClient creates services that share the same auth instance."""

    settings = PipefySettings(
        base_url="https://api.pipefy.com",
    )
    auth = StaticBearerAuth("shared-token")
    client = PipefyClient(settings=settings, auth=auth)

    assert isinstance(client._pipe_service, PipeService)
    assert isinstance(client._card_service, CardService)
    assert isinstance(client._member_service, MemberService)
    assert isinstance(client._webhook_service, WebhookService)
    assert client._member_service._pipe_service is client._pipe_service
    assert client._webhook_service._card_service is client._card_service
    assert isinstance(client._pipe_config_service, PipeConfigService)
    assert isinstance(client._table_service, TableService)
    assert isinstance(client._relation_service, RelationService)
    assert isinstance(client._automation_service, AutomationService)
    assert isinstance(client._ai_agent_service, AiAgentService)
    assert isinstance(client._attachment_service, AttachmentService)
    assert isinstance(client._introspection_service, SchemaIntrospectionService)
    # Converted public services share one GraphQL executor instance (one token cache).
    shared_executor = client._pipe_service._executor
    assert client._card_service._executor is shared_executor
    assert client._table_service._executor is shared_executor
    assert shared_executor.auth is auth


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
    client._relation_service = MagicMock()
    client._introspection_service = intro

    assert await client.introspect_type("Card") == {"name": "T"}
    intro.introspect_type.assert_awaited_once_with("Card", max_depth=1)

    assert await client.introspect_mutation("createCard") == {"name": "m"}
    intro.introspect_mutation.assert_awaited_once_with("createCard", max_depth=1)

    assert await client.search_schema("pipe") == {"types": []}
    intro.search_schema.assert_awaited_once_with("pipe", kind=None)

    assert await client.execute_graphql("query { x }", {"a": 1}) == {"data": True}
    intro.execute_graphql.assert_awaited_once_with("query { x }", {"a": 1})

    intro.execute_graphql.reset_mock()
    intro.execute_graphql.return_value = {"ok": 2}
    assert await client.execute_graphql("query { y }", None) == {"ok": 2}
    intro.execute_graphql.assert_awaited_once_with("query { y }", None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_ai_agent_write_methods_delegate_to_ai_agent_service():
    """Facade forwards create/update/toggle AI agent to AiAgentService."""
    from _shared.ai_agent_test_payloads import minimal_behavior_dict

    from pipefy_sdk.models.ai_agent import (
        BehaviorInput,
        CreateAiAgentInput,
        UpdateAiAgentInput,
    )

    ai_agent_service = AsyncMock()
    ai_agent_service.create_agent = AsyncMock(
        return_value={"agent_uuid": "new-1", "message": "created"}
    )
    ai_agent_service.update_agent = AsyncMock(
        return_value={"agent_uuid": "new-1", "message": "updated"}
    )
    ai_agent_service.toggle_agent_status = AsyncMock(
        return_value={"success": True, "message": "ok"}
    )

    client = PipefyClient.__new__(PipefyClient)
    client._ai_agent_service = ai_agent_service

    cin = CreateAiAgentInput(
        name="n",
        repo_uuid="00000000-0000-0000-0000-000000000001",
        instruction="purpose",
        behaviors=[
            BehaviorInput.model_validate(
                minimal_behavior_dict(name="b", event_id="evt")
            )
        ],
    )
    assert await client.create_ai_agent(cin) == {
        "agent_uuid": "new-1",
        "message": "created",
    }
    ai_agent_service.create_agent.assert_awaited_once_with(cin)

    uin = UpdateAiAgentInput(
        uuid="00000000-0000-0000-0000-000000000002",
        name="n",
        repo_uuid="00000000-0000-0000-0000-000000000001",
        behaviors=[
            BehaviorInput.model_validate(
                minimal_behavior_dict(name="b", event_id="evt")
            )
        ],
    )
    assert await client.update_ai_agent(uin) == {
        "agent_uuid": "new-1",
        "message": "updated",
    }
    # Facade now runs ``resolve_and_populate_field_refs`` before delegating, which
    # populates ``referencedFieldIds`` from the instruction (empty list for the
    # minimal behavior here). The service receives the prepared input, not the
    # raw one.
    ai_agent_service.update_agent.assert_awaited_once()
    forwarded = ai_agent_service.update_agent.await_args.args[0]
    assert isinstance(forwarded, UpdateAiAgentInput)
    assert forwarded.uuid == uin.uuid
    assert (
        forwarded.behaviors[0].action_params["aiBehaviorParams"]["referencedFieldIds"]
        == []
    )

    assert await client.toggle_ai_agent_status(agent_uuid="a", active=True) == {
        "success": True,
        "message": "ok",
    }
    ai_agent_service.toggle_agent_status.assert_awaited_once_with(
        agent_uuid="a", active=True
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_card_relation_delegates_to_internal_api_client(mock_settings):
    """delete_card_relation delegates to RelationService, which routes through the
    internal executor because the mutation is only on the internal GraphQL schema."""
    from graphql import print_ast

    from pipefy_sdk.queries.relation_queries import (
        INTERNAL_DELETE_CARD_RELATION_MUTATION,
    )

    client = PipefyClient(settings=mock_settings, auth=StaticBearerAuth("t"))
    # The facade and RelationService share the one internal executor, which
    # delegates to its shared endpoint; swap that endpoint's network seam.
    internal = client._internal_executor
    internal.endpoint.execute = AsyncMock(
        return_value={"deleteCardRelation": {"success": True}}
    )

    # Pin the snake_case input keys that the Internal API expects
    rendered = print_ast(INTERNAL_DELETE_CARD_RELATION_MUTATION.document)
    assert "child_id: $childId" in rendered
    assert "parent_id: $parentId" in rendered
    assert "source_id: $sourceId" in rendered

    result = await client.delete_card_relation("c1", "p2", "src-3")

    internal.endpoint.execute.assert_awaited_once_with(
        INTERNAL_DELETE_CARD_RELATION_MUTATION,
        {"childId": "c1", "parentId": "p2", "sourceId": "src-3"},
        auth=internal.auth,
    )
    assert result == {"deleteCardRelation": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sub_portal_mutation_routes_through_internal_api_client(mock_settings):
    """A sub-portal mutation reaches the Internal API client the facade builds at
    construction; PortalService and the facade share that one instance."""
    client = PipefyClient(settings=mock_settings, auth=StaticBearerAuth("t"))
    # PortalService and the facade share the one internal executor and its endpoint.
    internal = client._internal_executor
    internal.endpoint.execute = AsyncMock(
        return_value={"updateSubPortalElement": {"success": True}}
    )

    result = await client.publish_sub_portal("portal-1", "element-2", "sub-3")

    internal.endpoint.execute.assert_awaited()
    assert result == {"updateSubPortalElement": {"success": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_upload_attachment_delegates_to_attachment_service():
    """``client.upload_attachment`` forwards to ``AttachmentService.upload_attachment``."""
    from pathlib import Path

    from pipefy_sdk import Attachment, CardTarget

    sample = {
        "file_name": "x.txt",
        "content_type": "text/plain",
        "file_size": 3,
        "field_id": "f1",
        "storage_path": "p",
        "download_url": None,
    }

    attachment_service = AsyncMock()
    attachment_service.upload_attachment = AsyncMock(return_value=sample)

    client = PipefyClient.__new__(PipefyClient)
    client._attachment_service = attachment_service

    attachment = Attachment(path=Path("/tmp/x.txt"))
    target = CardTarget(card_id="c", field_id="f1")
    out = await client.upload_attachment(attachment, organization_id="o", target=target)

    assert out == sample
    attachment_service.upload_attachment.assert_awaited_once_with(
        attachment, organization_id="o", target=target
    )


@pytest.mark.unit
def test_attachment_service_receives_card_and_table_services_from_facade():
    """PipefyClient wires its own card_service and table_service into AttachmentService."""
    settings = PipefySettings(base_url="https://api.pipefy.com")
    client = PipefyClient(settings=settings, auth=StaticBearerAuth("t"))
    assert client._attachment_service._card_service is client._card_service
    assert client._attachment_service._table_service is client._table_service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_invite_members_propagates_value_error(mock_settings):
    member_service = AsyncMock()
    member_service.invite_members = AsyncMock(
        side_effect=ValueError("Invalid members[0]: expected valid email")
    )
    client = PipefyClient.__new__(PipefyClient)
    client._member_service = member_service
    with pytest.raises(ValueError, match="email"):
        await client.invite_members(
            "1",
            [{"email": "x", "role_name": "m"}],
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_automation_extra_input_camel_aliases_reach_service_as_api_names():
    """`extra_input` camelCase aliases are rewritten to the API field names (issue #275)."""
    automation_service = AsyncMock()
    automation_service.create_automation = AsyncMock(
        return_value={"ok": "create_automation"}
    )
    automation_service.update_automation = AsyncMock(
        return_value={"ok": "update_automation"}
    )
    client = PipefyClient.__new__(PipefyClient)
    client._automation_service = automation_service

    await client.create_automation(
        "p1",
        "Rule",
        "card_created",
        "move_single_card",
        extra_input={
            "actionParams": {"to_phase_id": "42"},
            "eventParams": {"to_phase_id": "7"},
        },
    )
    automation_service.create_automation.assert_awaited_once_with(
        "p1",
        "Rule",
        "card_created",
        "move_single_card",
        action_repo_id=None,
        active=True,
        action_params={"to_phase_id": "42"},
        event_params={"to_phase_id": "7"},
    )

    await client.update_automation(
        "a1", extra_input={"actionParams": {"card_id": "%{id}"}}
    )
    automation_service.update_automation.assert_awaited_once_with(
        "a1", action_params={"card_id": "%{id}"}
    )
