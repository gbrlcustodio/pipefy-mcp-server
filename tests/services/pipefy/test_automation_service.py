"""Unit tests for AutomationService (reads and writes)."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.services.pipefy.automation_service import AutomationService
from pipefy_mcp.services.pipefy.queries.automation_queries import (
    AUTOMATION_SIMULATION_QUERY,
    CREATE_AUTOMATION_MUTATION,
    CREATE_AUTOMATION_SIMULATION_MUTATION,
    DELETE_AUTOMATION_MUTATION,
    GET_AUTOMATION_ACTIONS_QUERY,
    GET_AUTOMATION_EVENTS_QUERY,
    GET_AUTOMATION_QUERY,
    GET_AUTOMATIONS_BY_ORG_QUERY,
    GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY,
    GET_PIPE_ORGANIZATION_ID_QUERY,
    UPDATE_AUTOMATION_MUTATION,
)
from pipefy_mcp.settings import PipefySettings


@pytest.fixture
def mock_settings():
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value: dict):
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_success(mock_settings):
    automation = {
        "id": "a1",
        "name": "Notify assignee",
        "active": True,
        "event_id": "card_moved",
        "action_id": "send_email_template",
        "actionEnabled": True,
        "disabledReason": None,
        "created_at": "2025-01-01",
        "event_repo": {"id": "p1", "name": "Pipe A"},
    }
    service = _make_service(mock_settings, {"automation": automation})
    result = await service.get_automation("101")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is GET_AUTOMATION_QUERY
    assert variables == {"id": 101}
    assert result["id"] == "a1"
    assert result["name"] == "Notify assignee"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_when_api_returns_null(mock_settings):
    service = _make_service(mock_settings, {"automation": None})
    result = await service.get_automation("999")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AUTOMATION_QUERY
    assert variables == {"id": 999}
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_transport_error(mock_settings):
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "not found"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_automation("998")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_success(mock_settings):
    rows = [
        {"id": "a1", "name": "Rule 1", "active": True},
        {"id": "a2", "name": "Rule 2", "active": False},
    ]
    service = _make_service(mock_settings, {"automations": {"nodes": rows}})
    result = await service.get_automations(organization_id="101", pipe_id="901")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY
    assert variables == {"organizationId": 101, "repoId": 901}
    assert isinstance(result, list)
    assert result == rows


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_success_resolves_org_from_pipe(mock_settings):
    rows = [{"id": "a1", "name": "Rule 1", "active": True}]
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=[
            {"pipe": {"organizationId": "300"}},
            {"automations": {"nodes": rows}},
        ],
    )
    result = await service.get_automations(pipe_id="901")

    assert service.execute_query.await_count == 2
    q1, v1 = service.execute_query.call_args_list[0][0]
    q2, v2 = service.execute_query.call_args_list[1][0]
    assert q1 is GET_PIPE_ORGANIZATION_ID_QUERY
    assert v1 == {"id": 901}
    assert q2 is GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY
    assert v2 == {"organizationId": 300, "repoId": 901}
    assert result == rows


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_organization_only_omits_repo_id(mock_settings):
    rows = [{"id": "a1", "name": "R", "active": True}]
    service = _make_service(mock_settings, {"automations": {"nodes": rows}})
    result = await service.get_automations(organization_id="201")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AUTOMATIONS_BY_ORG_QUERY
    assert variables == {"organizationId": 201}
    assert result == rows


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_both_none_returns_empty(mock_settings):
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock()
    result = await service.get_automations()
    service.execute_query.assert_not_called()
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_transport_error(mock_settings):
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_automations(organization_id="1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_actions_success(mock_settings):
    actions = [
        {
            "id": "act1",
            "icon": "mail",
            "enabled": True,
            "acceptedParameters": [],
            "disabledReason": None,
            "eventsBlacklist": [],
            "initiallyHidden": False,
            "triggerEvents": ["card_created"],
        }
    ]
    service = _make_service(mock_settings, {"automationActions": actions})
    result = await service.get_automation_actions("601")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AUTOMATION_ACTIONS_QUERY
    assert variables == {"repoId": 601}
    assert isinstance(result, list)
    assert result[0]["id"] == "act1"
    assert result[0]["enabled"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_actions_transport_error(mock_settings):
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "bad pipe"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_automation_actions("999")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_events_success(mock_settings):
    events = [
        {
            "id": "evt1",
            "icon": "check",
            "acceptedParameters": [],
            "actionsBlacklist": [],
        }
    ]
    service = _make_service(mock_settings, {"automationEvents": events})
    result = await service.get_automation_events("pipe-2")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_AUTOMATION_EVENTS_QUERY
    assert variables == {}
    assert isinstance(result, list)
    assert result == events


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_events_transport_error(mock_settings):
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "nope"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_automation_events("y")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_success(mock_settings):
    created = {
        "createAutomation": {
            "automation": {"id": "a-new", "name": "Notify", "active": True},
        },
    }
    service = _make_service(mock_settings, created)
    result = await service.create_automation(
        "p1",
        "Notify",
        "evt-1",
        "act-1",
    )

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_AUTOMATION_MUTATION
    inp = variables["input"]
    assert inp["name"] == "Notify"
    assert inp["action_id"] == "act-1"
    assert inp["event_id"] == "evt-1"
    assert inp["event_repo_id"] == "p1"
    assert inp["action_repo_id"] == "p1"
    assert inp["active"] is True
    assert result == created


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_with_action_repo_id(mock_settings):
    created = {
        "createAutomation": {
            "automation": {"id": "a-xpipe", "name": "Cross", "active": True},
        },
    }
    service = _make_service(mock_settings, created)
    await service.create_automation(
        "p-parent",
        "Cross",
        "evt-1",
        "act-connected",
        action_repo_id="p-child",
    )
    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["event_repo_id"] == "p-parent"
    assert inp["action_repo_id"] == "p-child"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_active_false_via_attrs(mock_settings):
    created = {
        "createAutomation": {
            "automation": {"id": "a2", "name": "Off", "active": False},
        },
    }
    service = _make_service(mock_settings, created)
    await service.create_automation("p1", "Off", "e", "a", **{"active": False})
    inp = service.execute_query.call_args[0][1]["input"]
    assert inp["active"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_transport_error(mock_settings):
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "reject"}])
    )
    with pytest.raises(TransportQueryError):
        await service.create_automation("p1", "N", "e", "a")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_raises_when_mutation_returns_error_details(
    mock_settings,
):
    payload = {
        "createAutomation": {
            "automation": None,
            "error_details": [
                {
                    "object_name": "Automation",
                    "messages": ["Invalid action for this event"],
                },
            ],
        },
    }
    service = _make_service(mock_settings, payload)
    with pytest.raises(ValueError, match="Invalid action"):
        await service.create_automation("p1", "N", "e", "a")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_raises_when_mutation_returns_error_details(
    mock_settings,
):
    payload = {
        "updateAutomation": {
            "automation": None,
            "error_details": [{"messages": ["Cannot rename inactive automation"]}],
        },
    }
    service = _make_service(mock_settings, payload)
    with pytest.raises(ValueError, match="Cannot rename"):
        await service.update_automation("a7", name="x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_success(mock_settings):
    updated = {"updateAutomation": {"automation": {"id": "a7", "name": "Renamed"}}}
    service = _make_service(mock_settings, updated)
    result = await service.update_automation("a7", name="Renamed")

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_AUTOMATION_MUTATION
    assert variables["input"] == {"id": "a7", "name": "Renamed"}
    assert result == updated


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_transport_error(mock_settings):
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "gone"}])
    )
    with pytest.raises(TransportQueryError):
        await service.update_automation("x", name="y")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_automation_success(mock_settings):
    deleted = {"deleteAutomation": {"success": True}}
    service = _make_service(mock_settings, deleted)
    result = await service.delete_automation("rm-1")

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_AUTOMATION_MUTATION
    assert variables["input"] == {"id": "rm-1"}
    assert result == {"success": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_automation_transport_error(mock_settings):
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "no access"}])
    )
    with pytest.raises(TransportQueryError):
        await service.delete_automation("z")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_simulate_automation_success(mock_settings):
    mutation_payload = {
        "createAutomationSimulation": {
            "simulationId": "sim-99",
            "clientMutationId": None,
        },
    }
    query_payload = {
        "automationSimulation": {
            "status": "success",
            "details": {"errorType": None, "message": "ok"},
            "simulationResult": {"preview": True},
        },
    }
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=[mutation_payload, query_payload])
    result = await service.simulate_automation(
        pipe_id="pipe-77",
        action_id="generate_with_ai",
        sample_card_id="card-1",
        event_id="card_created",
        event_params={"to_phase_id": "1"},
        name="Trial",
        extra_input={"active": True, "schedulerCron": "0 0 * * *"},
    )

    assert service.execute_query.await_count == 2
    q1, v1 = service.execute_query.call_args_list[0][0]
    q2, v2 = service.execute_query.call_args_list[1][0]
    assert q1 is CREATE_AUTOMATION_SIMULATION_MUTATION
    assert v1["input"]["action_id"] == "generate_with_ai"
    assert v1["input"]["sampleCardId"] == "card-1"
    assert v1["input"]["event_repo_id"] == "pipe-77"
    assert v1["input"]["action_repo_id"] == "pipe-77"
    assert v1["input"]["event_id"] == "card_created"
    assert v1["input"]["event_params"] == {"to_phase_id": "1"}
    assert v1["input"]["name"] == "Trial"
    assert v1["input"]["active"] is True
    assert v1["input"]["schedulerCron"] == "0 0 * * *"
    assert q2 is AUTOMATION_SIMULATION_QUERY
    assert v2 == {"simulationId": "sim-99"}
    assert result["simulation_id"] == "sim-99"
    assert result["automation_simulation"]["status"] == "success"
    assert result["automation_simulation"]["simulationResult"] == {"preview": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_simulate_automation_extra_input_overrides_repo_ids(mock_settings):
    mutation_payload = {
        "createAutomationSimulation": {
            "simulationId": "sim-override",
            "clientMutationId": None,
        },
    }
    query_payload = {
        "automationSimulation": {
            "status": "processing",
            "details": None,
            "simulationResult": None,
        },
    }
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=[mutation_payload, query_payload])
    await service.simulate_automation(
        pipe_id="default-pipe",
        action_id="generate_with_ai",
        sample_card_id="c1",
        extra_input={"event_repo_id": "ev-pipe", "action_repo_id": "act-pipe"},
    )
    _, v1 = service.execute_query.call_args_list[0][0]
    assert v1["input"]["event_repo_id"] == "ev-pipe"
    assert v1["input"]["action_repo_id"] == "act-pipe"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_simulate_automation_raises_when_no_simulation_id(mock_settings):
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        return_value={"createAutomationSimulation": {"simulationId": None}},
    )
    with pytest.raises(ValueError, match="simulationId"):
        await service.simulate_automation(
            pipe_id="p1",
            action_id="generate_with_ai",
            sample_card_id="1",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_simulate_automation_transport_error(mock_settings):
    service = AutomationService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.simulate_automation(
            pipe_id="p1",
            action_id="generate_with_ai",
            sample_card_id="1",
        )
