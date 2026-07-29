"""Tests for traditional automation MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import AutomationConditionInput, PipefyClient, PipefyGraphQLError

from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.automation_tools import AutomationTools
from tools.conftest import assert_invalid_arguments_envelope, build_tool_test_server


@pytest.fixture
def mock_automation_client():
    client = MagicMock(PipefyClient)
    client.get_automation = AsyncMock()
    client.get_automations = AsyncMock()
    client.get_automation_actions = AsyncMock()
    client.get_automation_events = AsyncMock()
    client.get_automation_event_attributes = AsyncMock()
    client.create_automation = AsyncMock()
    client.create_send_task_automation = AsyncMock()
    client.update_automation = AsyncMock()
    client.simulate_automation = AsyncMock()
    client.delete_automation = AsyncMock()
    client.get_phase_allowed_move_targets = AsyncMock()
    client.get_pipe_members = AsyncMock()
    return client


@pytest.fixture
def automation_mcp_server(mock_automation_client):
    return build_tool_test_server(
        "Automation Tools Test", AutomationTools.register, mock_automation_client
    )


@pytest.fixture
def automation_session(automation_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        automation_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_success(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automation.return_value = {
        "id": "a1",
        "name": "Rule",
        "active": True,
        "event_params": {"kindOfSla": "due_date", "triggerFieldIds": ["99"]},
        "action_params": {
            "aiParams": {"value": "Run prompt", "fieldIds": ["1"], "skillsIds": []},
        },
        "condition": {
            "id": "c1",
            "expressions": [
                {
                    "id": "e1",
                    "structure_id": "0",
                    "field_address": "900000101",
                    "operation": "equals",
                    "value": "yes",
                }
            ],
            "expressions_structure": [[0]],
        },
    }

    async with automation_session as session:
        result = await session.call_tool("get_automation", {"automation_id": "a1"})

    assert result.isError is False
    mock_automation_client.get_automation.assert_awaited_once_with("a1")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"] == mock_automation_client.get_automation.return_value
    assert payload["data"]["event_params"]["kindOfSla"] == "due_date"
    assert payload["data"]["action_params"]["aiParams"]["value"] == "Run prompt"
    assert payload["data"]["condition"]["expressions"][0]["operation"] == "equals"


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_graphql_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automation.side_effect = PipefyGraphQLError(
        [{"message": "not found"}]
    )

    async with automation_session as session:
        result = await session.call_tool("get_automation", {"automation_id": "x"})

    assert result.isError is False
    p = extract_payload(result)
    assert p["success"] is False
    assert "not found" in tool_error_message(p)


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_not_found_returns_empty_data_and_message(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automation.return_value = {}

    async with automation_session as session:
        result = await session.call_tool("get_automation", {"automation_id": "999"})

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"] == {}
    assert "No automation found" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_rejects_empty_automation_id(
    automation_session, mock_automation_client
):
    async with automation_session as session:
        result = await session.call_tool("get_automation", {"automation_id": ""})

    mock_automation_client.get_automation.assert_not_called()
    assert_invalid_arguments_envelope(result)


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_rejects_non_positive_int_id(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool("get_automation", {"automation_id": -1})

    mock_automation_client.get_automation.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automations_rejects_empty_string_filters(
    automation_session, mock_automation_client
):
    async with automation_session as session:
        result = await session.call_tool(
            "get_automations",
            {"organization_id": "", "pipe_id": ""},
        )

    mock_automation_client.get_automations.assert_not_called()
    assert_invalid_arguments_envelope(result)


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_rejects_empty_name(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "",
                "trigger_id": "e1",
                "action_id": "a1",
            },
        )

    mock_automation_client.create_automation.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "name" in tool_error_message(p).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_rejects_non_dict_extra_input(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "Rule",
                "trigger_id": "e1",
                "action_id": "a1",
                "extra_input": "not_a_dict",
            },
        )

    mock_automation_client.create_automation.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "extra_input" in tool_error_message(p).lower()
    assert "dict" in tool_error_message(p).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_delete_automation_rejects_invalid_id(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool("delete_automation", {"automation_id": -5})

    mock_automation_client.delete_automation.assert_not_called()
    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automations_success(
    automation_session, mock_automation_client, extract_payload
):
    rows = [{"id": "1", "name": "R1", "active": True}]
    mock_automation_client.get_automations.return_value = rows

    async with automation_session as session:
        result = await session.call_tool(
            "get_automations", {"organization_id": None, "pipe_id": "p9"}
        )

    assert result.isError is False
    mock_automation_client.get_automations.assert_awaited_once_with(
        organization_id=None, pipe_id="p9"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"] == rows


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automations_graphql_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automations.side_effect = PipefyGraphQLError(
        [{"message": "denied"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "get_automations",
            {"pipe_id": "bad"},
        )

    assert extract_payload(result)["success"] is False
    assert "denied" in tool_error_message(extract_payload(result))


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_actions_success(
    automation_session, mock_automation_client, extract_payload
):
    actions = [{"id": "act1", "label": "Email"}]
    mock_automation_client.get_automation_actions.return_value = actions

    async with automation_session as session:
        result = await session.call_tool(
            "get_automation_actions", {"pipe_id": "pipe-1"}
        )

    assert result.isError is False
    mock_automation_client.get_automation_actions.assert_awaited_once_with("pipe-1")
    assert extract_payload(result)["success"] is True
    assert extract_payload(result)["data"] == actions


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_actions_graphql_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automation_actions.side_effect = PipefyGraphQLError(
        [{"message": "bad pipe"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "get_automation_actions",
            {"pipe_id": "x"},
        )

    assert extract_payload(result)["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_events_success(
    automation_session, mock_automation_client, extract_payload
):
    events = [{"id": "e1", "label": "Done"}]
    mock_automation_client.get_automation_events.return_value = events

    async with automation_session as session:
        result = await session.call_tool("get_automation_events", {"pipe_id": "pipe-2"})

    assert result.isError is False
    mock_automation_client.get_automation_events.assert_awaited_once_with("pipe-2")
    assert extract_payload(result)["success"] is True
    assert extract_payload(result)["data"] == events


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_events_graphql_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.get_automation_events.side_effect = PipefyGraphQLError(
        [{"message": "nope"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "get_automation_events",
            {"pipe_id": "y"},
        )

    assert extract_payload(result)["success"] is False
    assert "nope" in tool_error_message(extract_payload(result))


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_get_automation_event_attributes_success(
    automation_session, mock_automation_client, extract_payload
):
    attributes = [
        {
            "id": "automation_event_execution_datetime",
            "internal_id": "automation_event_execution_datetime",
            "label": "Automation execution datetime",
            "type": "datetime",
            "value_token": "%{automation_event_execution_datetime}",
        }
    ]
    mock_automation_client.get_automation_event_attributes.return_value = attributes

    async with automation_session as session:
        result = await session.call_tool("get_automation_event_attributes", {})

    assert result.isError is False
    mock_automation_client.get_automation_event_attributes.assert_awaited_once_with()
    assert extract_payload(result)["success"] is True
    assert extract_payload(result)["data"] == attributes


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_read_automation_tools_have_read_only_hint(automation_session):
    async with automation_session as session:
        listed = await session.list_tools()
    names = {
        "get_automation",
        "get_automations",
        "get_automation_actions",
        "get_automation_events",
        "get_automation_event_attributes",
    }
    by_name = {t.name: t for t in listed.tools}
    for name in names:
        tool = by_name[name]
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_success(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_automation.return_value = {
        "createAutomation": {
            "automation": {"id": "a-new", "name": "Notify", "active": True},
        },
    }

    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "Notify",
                "trigger_id": "evt-1",
                "action_id": "act-1",
                "active": True,
                "extra_input": None,
                "debug": False,
            },
        )

    assert result.isError is False
    mock_automation_client.create_automation.assert_awaited_once_with(
        "p1",
        "Notify",
        "evt-1",
        "act-1",
        active=True,
        action_repo_id=None,
        condition=None,
        extra_input=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["automation"] == {
        "id": "a-new",
        "name": "Notify",
        "active": True,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_passes_typed_condition(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_automation.return_value = {
        "createAutomation": {"automation": {"id": "a-c", "name": "Gated"}}
    }
    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "Gated",
                "trigger_id": "evt-1",
                "action_id": "act-1",
                "condition": {
                    "expressions": [{"field_address": "9001", "operation": "present"}],
                    "expressions_structure": [[0]],
                },
            },
        )
    assert result.isError is False
    sent = mock_automation_client.create_automation.call_args.kwargs["condition"]
    assert isinstance(sent, AutomationConditionInput)
    assert sent.to_api_payload() == {
        "expressions": [{"field_address": "9001", "operation": "present"}],
        "expressions_structure": [[0]],
    }


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_invalid_condition_returns_error(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "Bad",
                "trigger_id": "evt-1",
                "action_id": "act-1",
                "condition": {"expressions": "not-a-list"},
            },
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "condition" in tool_error_message(payload).lower()
    mock_automation_client.create_automation.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_update_automation_passes_typed_condition(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.update_automation.return_value = {
        "updateAutomation": {"automation": {"id": "a7"}}
    }
    async with automation_session as session:
        result = await session.call_tool(
            "update_automation",
            {
                "automation_id": "a7",
                "condition": {
                    "expressions": [
                        {"field_address": "9001", "operation": "equals", "value": "x"}
                    ]
                },
            },
        )
    assert result.isError is False
    sent = mock_automation_client.update_automation.call_args.kwargs["condition"]
    assert isinstance(sent, AutomationConditionInput)
    assert sent.to_api_payload() == {
        "expressions": [{"field_address": "9001", "operation": "equals", "value": "x"}]
    }


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
@pytest.mark.parametrize("empty", [{}, {"expressions": []}])
async def test_create_automation_rejects_expressionless_condition(
    automation_session, mock_automation_client, extract_payload, empty
):
    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "Rule",
                "trigger_id": "evt-1",
                "action_id": "act-1",
                "condition": empty,
            },
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "expression" in tool_error_message(payload).lower()
    mock_automation_client.create_automation.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_update_automation_rejects_no_op(
    automation_session, mock_automation_client, extract_payload
):
    """An update with neither condition nor extra_input changes nothing — rejected."""
    async with automation_session as session:
        result = await session.call_tool("update_automation", {"automation_id": "a7"})
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "nothing to update" in tool_error_message(payload).lower()
    mock_automation_client.update_automation.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_surfaces_preflight_error_as_envelope(
    automation_session, mock_automation_client, extract_payload
):
    """MCP catches :class:`AutomationPreflightError` and renders the error envelope.

    The actual preflight logic lives in the SDK facade (see
    ``packages/sdk/tests/test_automation_preflight.py``); here we only verify the
    catch path on the MCP tool.
    """
    from pipefy_sdk.automation_preflight import AutomationPreflightError

    mock_automation_client.create_automation.side_effect = AutomationPreflightError(
        "This automation would move a card from phase id 10 to phase id 99, which is "
        "not an allowed transition."
    )

    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "Bad move",
                "trigger_id": "card_moved",
                "action_id": "move_single_card",
                "active": True,
                "action_repo_id": None,
                "extra_input": {
                    "event_params": {"to_phase_id": "10"},
                    "action_params": {"to_phase_id": "99"},
                },
                "debug": False,
            },
        )

    assert result.isError is False
    mock_automation_client.create_automation.assert_awaited_once()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "99" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_surfaces_field_map_preflight_error(
    automation_session, mock_automation_client, extract_payload
):
    from pipefy_sdk.automation_preflight import AutomationPreflightError

    mock_automation_client.create_automation.side_effect = AutomationPreflightError(
        'field_map fieldId "999999" was not found on pipe p1. '
        "Discover numeric internal_id values with get_start_form_fields(pipe_id) "
        "or get_phase_fields(phase_id)."
    )

    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "Bad field map",
                "trigger_id": "card_created",
                "action_id": "update_card_field",
                "active": False,
                "action_repo_id": None,
                "extra_input": {
                    "action_params": {
                        "card_id": "%{id}",
                        "field_map": [
                            {
                                "fieldId": "999999",
                                "inputMode": "copy_from",
                                "value": "%{created_at}",
                            },
                        ],
                    },
                },
                "debug": False,
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "999999" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_passes_action_repo_id(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_automation.return_value = {
        "createAutomation": {
            "automation": {"id": "a-cc", "name": "Connected", "active": True},
        },
    }

    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p-parent",
                "name": "Connected",
                "trigger_id": "1",
                "action_id": "2",
                "action_repo_id": "p-child",
                "extra_input": {
                    "action_params": {
                        "pipeId": "p-child",
                        "fieldsAttributes": [],
                    },
                },
            },
        )

    assert result.isError is False
    mock_automation_client.create_automation.assert_awaited_once_with(
        "p-parent",
        "Connected",
        "1",
        "2",
        active=True,
        action_repo_id="p-child",
        condition=None,
        extra_input={
            "action_params": {
                "pipeId": "p-child",
                "fieldsAttributes": [],
            },
        },
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_automation.side_effect = PipefyGraphQLError(
        [{"message": "invalid event"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "N",
                "trigger_id": "e",
                "action_id": "a",
            },
        )

    assert extract_payload(result)["success"] is False
    assert "invalid event" in tool_error_message(extract_payload(result))


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_error_only_diagnostic_markers_uses_fallback(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_automation.side_effect = PipefyGraphQLError(
        [{"message": "   ", "extensions": {"code": "X", "correlation_id": "Y"}}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "N",
                "trigger_id": "e",
                "action_id": "a",
            },
        )

    payload = extract_payload(result)
    msg = tool_error_message(payload)
    assert payload["success"] is False
    assert msg == "Automation request failed."
    assert "[code=" not in msg and "[correlation_id=" not in msg


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_error_only_markers_with_debug_keeps_fallback(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_automation.side_effect = PipefyGraphQLError(
        [{"message": "   ", "extensions": {"code": "X", "correlation_id": "Y"}}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "p1",
                "name": "N",
                "trigger_id": "e",
                "action_id": "a",
                "debug": True,
            },
        )

    msg = tool_error_message(extract_payload(result))
    assert msg.startswith("Automation request failed.")
    assert "(debug:" in msg and "codes=X" in msg
    assert "[code=" not in msg and "[correlation_id=" not in msg


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_update_automation_success(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.update_automation.return_value = {
        "updateAutomation": {
            "automation": {"id": "a7", "name": "Renamed", "active": False},
        },
    }

    async with automation_session as session:
        result = await session.call_tool(
            "update_automation",
            {
                "automation_id": "a7",
                "extra_input": {"name": "Renamed"},
                "debug": False,
            },
        )

    assert result.isError is False
    mock_automation_client.update_automation.assert_awaited_once_with(
        "a7",
        condition=None,
        extra_input={"name": "Renamed"},
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["automation"]["id"] == "a7"
    assert payload["automation"]["name"] == "Renamed"


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_update_automation_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.update_automation.side_effect = PipefyGraphQLError(
        [{"message": "not found"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "update_automation",
            {"automation_id": "missing", "extra_input": {"name": "x"}},
        )

    assert extract_payload(result)["success"] is False
    assert "not found" in tool_error_message(extract_payload(result))


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_delete_automation_success(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.delete_automation.return_value = {"success": True}

    async with automation_session as session:
        result = await session.call_tool(
            "delete_automation",
            {"automation_id": "rm-1", "confirm": True, "debug": False},
        )

    assert result.isError is False
    mock_automation_client.delete_automation.assert_awaited_once_with("rm-1")
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_delete_automation_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.delete_automation.side_effect = PipefyGraphQLError(
        [{"message": "forbidden"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "delete_automation",
            {"automation_id": "z", "confirm": True},
        )

    assert extract_payload(result)["success"] is False
    assert "forbidden" in tool_error_message(extract_payload(result))


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_delete_automation_has_destructive_hint(automation_session):
    async with automation_session as session:
        listed = await session.list_tools()
    delete_tool = next(t for t in listed.tools if t.name == "delete_automation")
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.destructiveHint is True
    assert delete_tool.annotations.readOnlyHint is False


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_and_update_automation_tools_are_not_read_only(
    automation_session,
):
    async with automation_session as session:
        listed = await session.list_tools()
    by_name = {t.name: t for t in listed.tools}
    for name in (
        "create_automation",
        "create_send_task_automation",
        "update_automation",
        "simulate_automation",
    ):
        ann = by_name[name].annotations
        assert ann is not None
        assert ann.readOnlyHint is False
        assert ann.destructiveHint is not True


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_simulate_automation_success(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.simulate_automation.return_value = {
        "simulation_id": "sim-1",
        "automation_simulation": {
            "status": "success",
            "details": {"message": "done"},
            "simulationResult": {"x": 1},
        },
    }

    async with automation_session as session:
        result = await session.call_tool(
            "simulate_automation",
            {
                "pipe_id": "p1",
                "action_id": "generate_with_ai",
                "sample_card_id": "c9",
                "event_id": "card_created",
                "event_params": None,
                "action_params": None,
                "condition": None,
                "name": None,
                "extra_input": None,
                "debug": False,
            },
        )

    assert result.isError is False
    mock_automation_client.simulate_automation.assert_awaited_once_with(
        pipe_id="p1",
        action_id="generate_with_ai",
        sample_card_id="c9",
        event_id="card_created",
        event_params=None,
        action_params=None,
        condition=None,
        name=None,
        extra_input=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["simulation_id"] == "sim-1"
    assert payload["automation_simulation"]["simulationResult"] == {"x": 1}


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_simulate_automation_graphql_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.simulate_automation.side_effect = PipefyGraphQLError(
        [{"message": "bad simulation"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "simulate_automation",
            {
                "pipe_id": "p1",
                "action_id": "generate_with_ai",
                "sample_card_id": "c1",
            },
        )

    assert extract_payload(result)["success"] is False
    assert "bad simulation" in tool_error_message(extract_payload(result))


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_simulate_automation_rejects_invalid_pipe_id(
    automation_session, mock_automation_client
):
    async with automation_session as session:
        result = await session.call_tool(
            "simulate_automation",
            {
                "pipe_id": "",
                "action_id": "generate_with_ai",
                "sample_card_id": "1",
            },
        )

    mock_automation_client.simulate_automation.assert_not_called()
    assert_invalid_arguments_envelope(result)


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_send_task_automation_success(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_send_task_automation.return_value = {
        "createAutomation": {
            "automation": {"id": "st-1", "name": "Notify owners", "active": True},
        },
    }

    async with automation_session as session:
        result = await session.call_tool(
            "create_send_task_automation",
            {
                "pipe_id": "p1",
                "name": "Notify owners",
                "event_id": "card_created",
                "task_title": "Review card",
                "recipients": "a@b.com, c@d.com",
            },
        )

    assert result.isError is False
    mock_automation_client.create_send_task_automation.assert_awaited_once_with(
        "p1",
        "Notify owners",
        "card_created",
        "Review card",
        "a@b.com, c@d.com",
        active=True,
        event_params=None,
        condition=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["automation"] == {
        "id": "st-1",
        "name": "Notify owners",
        "active": True,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_send_task_automation_passes_event_params_and_condition(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_send_task_automation.return_value = {
        "createAutomation": {
            "automation": {"id": "st-2", "name": "R", "active": True},
        },
    }
    event_params = {"to_phase_id": "ph-1"}
    condition = {"expressions": []}

    async with automation_session as session:
        result = await session.call_tool(
            "create_send_task_automation",
            {
                "pipe_id": "p1",
                "name": "R",
                "event_id": "card_moved",
                "task_title": "T",
                "recipients": "x@y.com",
                "event_params": event_params,
                "condition": condition,
            },
        )

    assert result.isError is False
    mock_automation_client.create_send_task_automation.assert_awaited_once_with(
        "p1",
        "R",
        "card_moved",
        "T",
        "x@y.com",
        active=True,
        event_params=event_params,
        condition=condition,
    )
    assert extract_payload(result)["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_send_task_automation_validation_blank_task_title(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool(
            "create_send_task_automation",
            {
                "pipe_id": "p1",
                "name": "N",
                "event_id": "card_created",
                "task_title": "",
                "recipients": "a@b.com",
            },
        )

    mock_automation_client.create_send_task_automation.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_send_task_automation_validation_scheduler(
    automation_session, mock_automation_client, extract_payload
):
    async with automation_session as session:
        result = await session.call_tool(
            "create_send_task_automation",
            {
                "pipe_id": "p1",
                "name": "N",
                "event_id": "scheduler",
                "task_title": "T",
                "recipients": "a@b.com",
            },
        )

    mock_automation_client.create_send_task_automation.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "send_a_task" in tool_error_message(p)


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_send_task_automation_graphql_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_send_task_automation.side_effect = PipefyGraphQLError(
        [{"message": "mutation blocked"}]
    )

    async with automation_session as session:
        result = await session.call_tool(
            "create_send_task_automation",
            {
                "pipe_id": "p1",
                "name": "N",
                "event_id": "card_created",
                "task_title": "T",
                "recipients": "a@b.com",
            },
        )

    assert extract_payload(result)["success"] is False
    assert "mutation blocked" in tool_error_message(extract_payload(result))


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_send_task_automation_listed_not_read_only(automation_session):
    async with automation_session as session:
        listed = await session.list_tools()
    tool = next(t for t in listed.tools if t.name == "create_send_task_automation")
    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is False
    assert tool.annotations.destructiveHint is not True


## ---------------------------------------------------------------------------
## Cross-pipe PERMISSION_DENIED enrichment
## ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("automation_session", [None], indirect=True)
async def test_create_automation_cross_pipe_permission_denied_enriches_error(
    automation_session, mock_automation_client, extract_payload
):
    mock_automation_client.create_automation.side_effect = PipefyGraphQLError(
        [
            {
                "message": "forbidden",
                "extensions": {"code": "PERMISSION_DENIED"},
            }
        ]
    )
    # get_pipe_members fails for the target pipe
    mock_automation_client.get_pipe_members.side_effect = RuntimeError("no access")
    async with automation_session as session:
        result = await session.call_tool(
            "create_automation",
            {
                "pipe_id": "100",
                "name": "Cross-pipe rule",
                "trigger_id": "card_created",
                "action_id": "move_card",
                "action_repo_id": "200",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    # Cross-pipe permission-denied enrichment ran (prepends membership hint via
    # the async enrich_permission_denied_error at the call site).
    assert "invite_members" in tool_error_message(payload)
    # handle_automation_tool_graphql_error's ambiguity enricher also ran
    # (rewrites the raw "forbidden" into a dual-meaning NOT_FOUND/denied hint).
    assert "may lack access" in tool_error_message(payload)
    assert payload["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.anyio
class TestCreateSendTaskAutomationActiveFlag:
    """Verify the ``active`` flag is forwarded to AutomationService.create_send_task_automation."""

    @pytest.mark.parametrize("automation_session", [None], indirect=True)
    async def test_active_false_is_forwarded(
        self, automation_session, mock_automation_client, extract_payload
    ):
        mock_automation_client.create_send_task_automation.return_value = {
            "createAutomation": {
                "automation": {"id": "st-d", "name": "Disabled", "active": False},
            },
        }
        async with automation_session as session:
            result = await session.call_tool(
                "create_send_task_automation",
                {
                    "pipe_id": "p1",
                    "name": "Disabled",
                    "event_id": "card_created",
                    "task_title": "Do",
                    "recipients": "a@b.c",
                    "active": False,
                },
            )
        assert result.isError is False
        kwargs = mock_automation_client.create_send_task_automation.await_args.kwargs
        assert kwargs["active"] is False

    @pytest.mark.parametrize("automation_session", [None], indirect=True)
    async def test_default_active_true(
        self, automation_session, mock_automation_client, extract_payload
    ):
        mock_automation_client.create_send_task_automation.return_value = {
            "createAutomation": {
                "automation": {"id": "st-a", "name": "Active", "active": True},
            },
        }
        async with automation_session as session:
            result = await session.call_tool(
                "create_send_task_automation",
                {
                    "pipe_id": "p1",
                    "name": "Active",
                    "event_id": "card_created",
                    "task_title": "Do",
                    "recipients": "a@b.c",
                },
            )
        assert result.isError is False
        kwargs = mock_automation_client.create_send_task_automation.await_args.kwargs
        assert kwargs["active"] is True


@pytest.mark.anyio
class TestPipefyIdCoercion:
    """PipefyId coerces int IDs to str at the tool boundary."""

    @pytest.mark.parametrize("automation_session", [None], indirect=True)
    async def test_get_automation_coerces_int_automation_id(
        self, automation_session, mock_automation_client, extract_payload
    ):
        mock_automation_client.get_automation = AsyncMock(
            return_value={"id": "500", "name": "Test"}
        )
        async with automation_session as session:
            result = await session.call_tool("get_automation", {"automation_id": 500})
        assert result.isError is False
        mock_automation_client.get_automation.assert_awaited_once_with("500")
