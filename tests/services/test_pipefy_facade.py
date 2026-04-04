from unittest.mock import AsyncMock, MagicMock

import pytest

from pipefy_mcp.services.pipefy.ai_agent_service import AiAgentService
from pipefy_mcp.services.pipefy.automation_service import AutomationService
from pipefy_mcp.services.pipefy.card_service import CardService
from pipefy_mcp.services.pipefy.client import PipefyClient
from pipefy_mcp.services.pipefy.member_service import MemberService
from pipefy_mcp.services.pipefy.pipe_config_service import PipeConfigService
from pipefy_mcp.services.pipefy.pipe_service import PipeService
from pipefy_mcp.services.pipefy.relation_service import RelationService
from pipefy_mcp.services.pipefy.schema_introspection_service import (
    SchemaIntrospectionService,
)
from pipefy_mcp.services.pipefy.table_service import TableService
from pipefy_mcp.services.pipefy.webhook_service import WebhookService
from pipefy_mcp.settings import PipefySettings


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_facade_delegates_to_services_without_modifying_args_or_return():
    """Test PipefyClient is a pure facade: delegates calls unchanged to services."""
    pipe_service = AsyncMock()
    card_service = AsyncMock()
    pipe_config_service = AsyncMock()
    table_service = AsyncMock()

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
    pipe_config_service.create_field_condition = AsyncMock(
        return_value={"ok": "create_field_condition"}
    )
    pipe_config_service.update_field_condition = AsyncMock(
        return_value={"ok": "update_field_condition"}
    )
    pipe_config_service.delete_field_condition = AsyncMock(
        return_value={"ok": "delete_field_condition"}
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
    automation_service.create_automation = AsyncMock(
        return_value={"ok": "create_automation"}
    )
    automation_service.update_automation = AsyncMock(
        return_value={"ok": "update_automation"}
    )
    automation_service.delete_automation = AsyncMock(
        return_value={"ok": "delete_automation"}
    )

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
    client._automation_service = automation_service
    client._ai_agent_service = ai_agent_service

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
    pipe_config_service.delete_phase_field.assert_awaited_once_with(13)

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

    assert await client.delete_table_field(9) == {"ok": "delete_table_field"}
    table_service.delete_table_field.assert_awaited_once_with(9)

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
        "p1",
        "Rule",
        "ev",
        "act",
        active=True,
        extra_input={"active": False},
    ) == {"ok": "create_automation"}
    automation_service.create_automation.assert_awaited_with(
        "p1", "Rule", "ev", "act", action_repo_id=None, active=False
    )

    assert await client.create_automation(
        "p1", "Rule", "ev", "act", action_repo_id="child-pipe"
    ) == {"ok": "create_automation"}
    automation_service.create_automation.assert_awaited_with(
        "p1", "Rule", "ev", "act", action_repo_id="child-pipe", active=True
    )

    assert await client.update_automation("a1", extra_input={"name": "N"}) == {
        "ok": "update_automation"
    }
    automation_service.update_automation.assert_awaited_once_with("a1", name="N")

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
    assert isinstance(client._member_service, MemberService)
    assert isinstance(client._webhook_service, WebhookService)
    assert client._member_service._pipe_service is client._pipe_service
    assert client._webhook_service._card_service is client._card_service
    assert isinstance(client._pipe_config_service, PipeConfigService)
    assert isinstance(client._table_service, TableService)
    assert isinstance(client._relation_service, RelationService)
    assert isinstance(client._automation_service, AutomationService)
    assert isinstance(client._ai_agent_service, AiAgentService)
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
    assert client._table_service._auth is not None, (
        "TableService should have an auth instance"
    )
    assert client._relation_service._auth is not None, (
        "RelationService should have an auth instance"
    )
    assert client._automation_service._auth is not None, (
        "AutomationService should have an auth instance"
    )
    assert client._ai_agent_service._auth is not None, (
        "AiAgentService should have an auth instance"
    )
    assert client._pipe_config_service._auth is client._ai_agent_service._auth
    assert client._pipe_service._auth is client._card_service._auth
    assert client._pipe_service._auth is client._pipe_config_service._auth
    assert client._pipe_service._auth is client._table_service._auth
    assert client._pipe_service._auth is client._relation_service._auth
    assert client._pipe_service._auth is client._automation_service._auth
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
    client._relation_service = MagicMock()
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_ai_agent_write_methods_delegate_to_ai_agent_service():
    """Facade forwards create/update/toggle AI agent to AiAgentService."""
    from pipefy_mcp.models.ai_agent import (
        BehaviorInput,
        CreateAiAgentInput,
        UpdateAiAgentInput,
    )
    from tests.ai_agent_test_payloads import minimal_behavior_dict

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
    ai_agent_service.update_agent.assert_awaited_once_with(uin)

    assert await client.toggle_ai_agent_status(agent_uuid="a", active=True) == {
        "success": True,
        "message": "ok",
    }
    ai_agent_service.toggle_agent_status.assert_awaited_once_with(
        agent_uuid="a", active=True
    )
