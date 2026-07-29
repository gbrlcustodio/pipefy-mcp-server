"""Unit tests for AutomationService (reads and writes)."""

from unittest.mock import AsyncMock

import pytest
from _shared.mock_clients import mock_executor
from graphql import print_ast

from pipefy_sdk import PipefyGraphQLError
from pipefy_sdk.queries.automation_queries import (
    AUTOMATION_SIMULATION_QUERY,
    CREATE_AUTOMATION_MUTATION,
    CREATE_AUTOMATION_SIMULATION_MUTATION,
    DELETE_AUTOMATION_MUTATION,
    GET_AUTOMATION_ACTIONS_QUERY,
    GET_AUTOMATION_EVENT_ATTRIBUTES_QUERY,
    GET_AUTOMATION_EVENTS_QUERY,
    GET_AUTOMATION_QUERY,
    GET_AUTOMATIONS_BY_ORG_QUERY,
    GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY,
    GET_PIPE_ORGANIZATION_ID_QUERY,
    UPDATE_AUTOMATION_MUTATION,
)
from pipefy_sdk.services.automation_service import (
    AutomationService,
    _format_automation_error_details,
    normalize_automation_event_attributes,
)

## ---------------------------------------------------------------------------
## _format_automation_error_details edge cases
## ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatAutomationErrorDetails:
    def test_none_returns_empty(self):
        assert _format_automation_error_details(None) == ""

    def test_string_passthrough(self):
        assert _format_automation_error_details("some error") == "some error"

    def test_dict_with_messages_list(self):
        result = _format_automation_error_details({"messages": ["a", "b"]})
        assert result == "a; b"

    def test_dict_without_messages_falls_back_to_str(self):
        result = _format_automation_error_details({"code": 42})
        assert "42" in result

    def test_list_of_strings(self):
        result = _format_automation_error_details(["error one", "error two"])
        assert result == "error one; error two"

    def test_list_of_dicts_with_object_name_and_key(self):
        result = _format_automation_error_details(
            [
                {
                    "object_name": "Automation",
                    "object_key": "a1",
                    "messages": ["bad field"],
                }
            ]
        )
        assert result == "Automation (a1): bad field"

    def test_list_of_dicts_with_object_name_only(self):
        result = _format_automation_error_details(
            [{"object_name": "Rule", "messages": ["invalid"]}]
        )
        assert result == "Rule: invalid"

    def test_list_of_dicts_with_object_key_only(self):
        result = _format_automation_error_details(
            [{"object_key": "k1", "messages": ["whoops"]}]
        )
        assert result == "k1: whoops"

    def test_list_of_dicts_with_single_message_field(self):
        result = _format_automation_error_details([{"message": "single error"}])
        assert result == "single error"

    def test_list_skips_non_dict_non_string_items(self):
        result = _format_automation_error_details([42, None, "hello"])
        assert result == "hello"

    def test_list_skips_dicts_without_messages(self):
        result = _format_automation_error_details([{"code": 1}])
        assert result == ""

    def test_unknown_type_returns_str(self):
        result = _format_automation_error_details(12345)
        assert result == "12345"

    def test_list_filters_empty_strings_in_messages(self):
        result = _format_automation_error_details(
            [{"messages": ["", "real error", ""]}]
        )
        assert result == "real error"


## ---------------------------------------------------------------------------
## Service tests
## ---------------------------------------------------------------------------


def _make_service(return_value: dict):
    executor = mock_executor(return_value)
    service = AutomationService(executor=executor)
    return service, executor


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_success():
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
        "event_params": {
            "to_phase_id": "ph_dest",
            "triggerFieldIds": ["f1", "f2"],
            "phase": {"id": "ph1", "name": "Doing"},
        },
        "action_params": {
            "aiParams": {
                "value": "Summarize card",
                "fieldIds": ["10"],
                "skillsIds": ["20"],
            },
            "email_template_id": "tmpl-1",
            "to_phase_id": "ph2",
        },
        "condition": {
            "id": "cond-1",
            "expressions": [
                {
                    "id": "expr-1",
                    "structure_id": "0",
                    "field_address": "900000101",
                    "operation": "equals",
                    "value": "approved",
                }
            ],
            "expressions_structure": [[0]],
        },
    }
    service, executor = _make_service({"automation": automation})
    result = await service.get_automation("101")

    executor.execute_query.assert_awaited_once()
    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AUTOMATION_QUERY
    assert "condition" in print_ast(GET_AUTOMATION_QUERY.document)
    assert variables == {"id": "101"}
    assert result["id"] == "a1"
    assert result["name"] == "Notify assignee"
    assert result["event_params"]["to_phase_id"] == "ph_dest"
    assert result["event_params"]["triggerFieldIds"] == ["f1", "f2"]
    assert result["action_params"]["aiParams"]["value"] == "Summarize card"
    assert result["action_params"]["aiParams"]["fieldIds"] == ["10"]
    assert result["condition"]["id"] == "cond-1"
    assert result["condition"]["expressions"][0]["operation"] == "equals"
    assert result["condition"]["expressions_structure"] == [[0]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_when_api_returns_null():
    service, executor = _make_service({"automation": None})
    result = await service.get_automation("999")

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AUTOMATION_QUERY
    assert variables == {"id": "999"}
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "not found"}]))
    service = AutomationService(executor=executor)
    with pytest.raises(PipefyGraphQLError):
        await service.get_automation("998")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_success():
    rows = [
        {"id": "a1", "name": "Rule 1", "active": True},
        {"id": "a2", "name": "Rule 2", "active": False},
    ]
    service, executor = _make_service({"automations": {"nodes": rows}})
    result = await service.get_automations(organization_id="101", pipe_id="901")

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY
    assert variables == {"organizationId": "101", "repoId": "901"}
    assert isinstance(result, list)
    assert result == rows


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_success_resolves_org_from_pipe():
    rows = [{"id": "a1", "name": "Rule 1", "active": True}]
    executor = mock_executor(
        side_effect=[
            {"pipe": {"organizationId": "300"}},
            {"automations": {"nodes": rows}},
        ],
    )
    service = AutomationService(executor=executor)
    result = await service.get_automations(pipe_id="901")

    assert executor.execute_query.await_count == 2
    q1, v1 = executor.execute_query.call_args_list[0][0]
    q2, v2 = executor.execute_query.call_args_list[1][0]
    assert q1 is GET_PIPE_ORGANIZATION_ID_QUERY
    assert v1 == {"id": "901"}
    assert q2 is GET_AUTOMATIONS_FOR_ORG_AND_REPO_QUERY
    assert v2 == {"organizationId": "300", "repoId": "901"}
    assert result == rows


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_organization_only_omits_repo_id():
    rows = [{"id": "a1", "name": "R", "active": True}]
    service, executor = _make_service({"automations": {"nodes": rows}})
    result = await service.get_automations(organization_id="201")

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AUTOMATIONS_BY_ORG_QUERY
    assert variables == {"organizationId": "201"}
    assert result == rows


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_pipe_only_org_not_found_returns_empty():
    """When pipe_id is given but org lookup returns no organizationId, return empty."""
    executor = mock_executor({"pipe": {"organizationId": None}})
    service = AutomationService(executor=executor)
    result = await service.get_automations(pipe_id="100")
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_pipe_only_pipe_missing_returns_empty():
    """When pipe lookup returns no pipe key at all, return empty."""
    executor = mock_executor({"pipe": None})
    service = AutomationService(executor=executor)
    result = await service.get_automations(pipe_id="100")
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_null_nodes_returns_empty():
    service, _ = _make_service({"automations": {"nodes": None}})
    result = await service.get_automations(organization_id="1")
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_null_connection_returns_empty():
    service, _ = _make_service({"automations": None})
    result = await service.get_automations(organization_id="1")
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_actions_null_returns_empty():
    service, _ = _make_service({"automationActions": None})
    result = await service.get_automation_actions("100")
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_events_null_returns_empty():
    service, _ = _make_service({"automationEvents": None})
    result = await service.get_automation_events("100")
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_both_none_returns_empty():
    executor = mock_executor()
    service = AutomationService(executor=executor)
    result = await service.get_automations()
    executor.execute_query.assert_not_called()
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automations_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "denied"}]))
    service = AutomationService(executor=executor)
    with pytest.raises(PipefyGraphQLError):
        await service.get_automations(organization_id="1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_actions_success():
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
    service, executor = _make_service({"automationActions": actions})
    result = await service.get_automation_actions("601")

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AUTOMATION_ACTIONS_QUERY
    assert variables == {"repoId": "601"}
    assert isinstance(result, list)
    assert result[0]["id"] == "act1"
    assert result[0]["enabled"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_actions_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "bad pipe"}]))
    service = AutomationService(executor=executor)
    with pytest.raises(PipefyGraphQLError):
        await service.get_automation_actions("999")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_events_success():
    events = [
        {
            "id": "evt1",
            "icon": "check",
            "acceptedParameters": [],
            "actionsBlacklist": [],
        }
    ]
    service, executor = _make_service({"automationEvents": events})
    result = await service.get_automation_events("pipe-2")

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AUTOMATION_EVENTS_QUERY
    assert variables == {}
    assert isinstance(result, list)
    assert result == events


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_events_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "nope"}]))
    service = AutomationService(executor=executor)
    with pytest.raises(PipefyGraphQLError):
        await service.get_automation_events("y")


@pytest.mark.unit
class TestNormalizeAutomationEventAttributes:
    def test_maps_execution_datetime_row(self):
        raw = {
            "automationEventExecutionDatetime": {
                "internalId": "automation_event_execution_datetime",
                "label": "Automation execution datetime",
                "type": "datetime",
            }
        }
        rows = normalize_automation_event_attributes(raw)
        assert rows == [
            {
                "id": "automation_event_execution_datetime",
                "internal_id": "automation_event_execution_datetime",
                "label": "Automation execution datetime",
                "type": "datetime",
                "value_token": "%{automation_event_execution_datetime}",
            }
        ]

    def test_none_or_empty_returns_empty(self):
        assert normalize_automation_event_attributes(None) == []
        assert normalize_automation_event_attributes({}) == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_event_attributes_null_returns_empty():
    service, _ = _make_service({"automationEventAttributes": None})
    result = await service.get_automation_event_attributes()
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_event_attributes_success():
    graphql_payload = {
        "automationEventAttributes": {
            "automationEventExecutionDatetime": {
                "internalId": "automation_event_execution_datetime",
                "label": "Automation execution datetime",
                "type": "datetime",
            }
        }
    }
    service, executor = _make_service(graphql_payload)
    result = await service.get_automation_event_attributes()

    query, variables = executor.execute_query.call_args[0]
    assert query is GET_AUTOMATION_EVENT_ATTRIBUTES_QUERY
    assert variables == {}
    assert result == [
        {
            "id": "automation_event_execution_datetime",
            "internal_id": "automation_event_execution_datetime",
            "label": "Automation execution datetime",
            "type": "datetime",
            "value_token": "%{automation_event_execution_datetime}",
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_event_attributes_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "denied"}]))
    service = AutomationService(executor=executor)
    with pytest.raises(PipefyGraphQLError):
        await service.get_automation_event_attributes()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_success():
    created = {
        "createAutomation": {
            "automation": {"id": "a-new", "name": "Notify", "active": True},
        },
    }
    service, executor = _make_service(created)
    result = await service.create_automation(
        "p1",
        "Notify",
        "evt-1",
        "act-1",
    )

    executor.execute_query.assert_awaited_once()
    query, variables = executor.execute_query.call_args[0]
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
async def test_create_automation_with_action_repo_id():
    created = {
        "createAutomation": {
            "automation": {"id": "a-xpipe", "name": "Cross", "active": True},
        },
    }
    service, executor = _make_service(created)
    await service.create_automation(
        "p-parent",
        "Cross",
        "evt-1",
        "act-connected",
        action_repo_id="p-child",
    )
    inp = executor.execute_query.call_args[0][1]["input"]
    assert inp["event_repo_id"] == "p-parent"
    assert inp["action_repo_id"] == "p-child"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_active_false_via_attrs():
    created = {
        "createAutomation": {
            "automation": {"id": "a2", "name": "Off", "active": False},
        },
    }
    service, executor = _make_service(created)
    await service.create_automation("p1", "Off", "e", "a", **{"active": False})
    inp = executor.execute_query.call_args[0][1]["input"]
    assert inp["active"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_send_task_automation_builds_task_params():
    """Service builds ``action_params.taskParams`` and delegates to ``create_automation``."""
    created = {
        "createAutomation": {
            "automation": {"id": "st-1", "name": "Notify", "active": True},
        },
    }
    service, executor = _make_service(created)

    result = await service.create_send_task_automation(
        "pipe-1",
        "Notify owners",
        "card_created",
        "Review card",
        "a@b.com, c@d.com",
    )

    inp = executor.execute_query.call_args[0][1]["input"]
    assert inp["action_id"] == "send_a_task"
    assert inp["event_id"] == "card_created"
    assert inp["event_repo_id"] == "pipe-1"
    assert inp["action_repo_id"] == "pipe-1"
    assert inp["action_params"] == {
        "taskParams": {
            "title": "Review card",
            "recipients": "a@b.com, c@d.com",
        },
    }
    assert "event_params" not in inp
    assert "condition" not in inp
    assert result == created


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_send_task_automation_includes_event_params_and_condition():
    """Optional ``event_params`` and ``condition`` are merged when provided."""
    service, executor = _make_service(
        {"createAutomation": {"automation": {"id": "st-2", "active": True}}},
    )
    event_params = {"to_phase_id": "ph-1"}
    condition = {"expressions": [{"field_address": "f", "value": "v"}]}

    await service.create_send_task_automation(
        "pipe-1",
        "R",
        "card_moved",
        "T",
        "x@y.com",
        active=False,
        event_params=event_params,
        condition=condition,
    )

    inp = executor.execute_query.call_args[0][1]["input"]
    assert inp["event_params"] == event_params
    assert inp["condition"] == condition
    assert inp["active"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "reject"}]))
    service = AutomationService(executor=executor)
    with pytest.raises(PipefyGraphQLError):
        await service.create_automation("p1", "N", "e", "a")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_automation_raises_when_mutation_returns_error_details():
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
    service, _ = _make_service(payload)
    with pytest.raises(ValueError, match="Invalid action"):
        await service.create_automation("p1", "N", "e", "a")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_raises_when_mutation_returns_error_details():
    payload = {
        "updateAutomation": {
            "automation": None,
            "error_details": [{"messages": ["Cannot rename inactive automation"]}],
        },
    }
    service, _ = _make_service(payload)
    with pytest.raises(ValueError, match="Cannot rename"):
        await service.update_automation("a7", name="x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_success():
    updated = {"updateAutomation": {"automation": {"id": "a7", "name": "Renamed"}}}
    service, executor = _make_service(updated)
    result = await service.update_automation("a7", name="Renamed")

    query, variables = executor.execute_query.call_args[0]
    assert query is UPDATE_AUTOMATION_MUTATION
    assert variables["input"] == {"id": "a7", "name": "Renamed"}
    assert result == updated


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_automation_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "gone"}]))
    service = AutomationService(executor=executor)
    with pytest.raises(PipefyGraphQLError):
        await service.update_automation("x", name="y")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_automation_success():
    deleted = {"deleteAutomation": {"success": True}}
    service, executor = _make_service(deleted)
    result = await service.delete_automation("rm-1")

    query, variables = executor.execute_query.call_args[0]
    assert query is DELETE_AUTOMATION_MUTATION
    assert variables["input"] == {"id": "rm-1"}
    assert result == {"success": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_automation_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "no access"}]))
    service = AutomationService(executor=executor)
    with pytest.raises(PipefyGraphQLError):
        await service.delete_automation("z")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_simulate_automation_success():
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
    executor = mock_executor(side_effect=[mutation_payload, query_payload])
    service = AutomationService(executor=executor)
    result = await service.simulate_automation(
        pipe_id="pipe-77",
        action_id="generate_with_ai",
        sample_card_id="card-1",
        event_id="card_created",
        event_params={"to_phase_id": "1"},
        name="Trial",
        extra_input={"active": True, "schedulerCron": "0 0 * * *"},
    )

    assert executor.execute_query.await_count == 2
    q1, v1 = executor.execute_query.call_args_list[0][0]
    q2, v2 = executor.execute_query.call_args_list[1][0]
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
async def test_simulate_automation_extra_input_overrides_repo_ids():
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
    executor = mock_executor(side_effect=[mutation_payload, query_payload])
    service = AutomationService(executor=executor)
    await service.simulate_automation(
        pipe_id="default-pipe",
        action_id="generate_with_ai",
        sample_card_id="c1",
        extra_input={"event_repo_id": "ev-pipe", "action_repo_id": "act-pipe"},
    )
    _, v1 = executor.execute_query.call_args_list[0][0]
    assert v1["input"]["event_repo_id"] == "ev-pipe"
    assert v1["input"]["action_repo_id"] == "act-pipe"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_simulate_automation_raises_when_no_simulation_id():
    executor = mock_executor(
        {"createAutomationSimulation": {"simulationId": None}},
    )
    service = AutomationService(executor=executor)
    with pytest.raises(ValueError, match="simulationId"):
        await service.simulate_automation(
            pipe_id="p1",
            action_id="generate_with_ai",
            sample_card_id="1",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_simulate_automation_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "denied"}]))
    service = AutomationService(executor=executor)
    with pytest.raises(PipefyGraphQLError):
        await service.simulate_automation(
            pipe_id="p1",
            action_id="generate_with_ai",
            sample_card_id="1",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_automation_logs_by_repo_skips_graphql_when_pipe_has_no_automations():
    """Facade short-circuits before automationLogsByRepo when ``get_automations`` is empty."""
    from pipefy_sdk.client import PipefyClient

    client = PipefyClient.__new__(PipefyClient)
    client.get_automations = AsyncMock(return_value=[])
    obs = AsyncMock()
    obs.get_automation_logs_by_repo = AsyncMock(
        return_value={"automationLogsByRepo": {"should_not": "call"}}
    )
    client._observability_service = obs

    out = await PipefyClient.get_automation_logs_by_repo(
        client, "repo-77", first=10, after="c0"
    )
    obs.get_automation_logs_by_repo.assert_not_called()
    assert out["automationLogsByRepo"]["nodes"] == []
    assert out["automationLogsByRepo"]["totalCount"] == 0
    assert out["automationLogsByRepo"]["pageInfo"]["hasNextPage"] is False
