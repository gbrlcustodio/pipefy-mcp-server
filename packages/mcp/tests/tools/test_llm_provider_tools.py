"""Tests for LLM provider discovery MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient, PipefyGraphQLError

from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.llm_provider_tools import LlmProviderTools
from tools.conftest import build_tool_test_server

BYOM_NODE = {
    "__typename": "LlmProvider",
    "id": "42",
    "name": "Azure custom",
    "type": "byom",
    "active": True,
    "organizationDefault": False,
    "configuration": {"auth": {"accessToken": "__REDACTED__"}},
}

SYSTEM_NODE = {
    "__typename": "SystemLlmProvider",
    "id": "7",
    "name": "Pipefy GPT",
    "type": "system",
    "organizationDefault": True,
    "systemDefault": True,
    "state": "active",
    "description": "Managed model",
    "aiCredits": 2,
    "deprecationDate": None,
    "configuration": {"model": "gpt-4o"},
}


def permission_denied_error() -> PipefyGraphQLError:
    return PipefyGraphQLError(
        [
            {
                "message": "Permission denied",
                "extensions": {"code": "PERMISSION_DENIED", "correlation_id": "corr-9"},
            }
        ]
    )


def not_found_error() -> PipefyGraphQLError:
    return PipefyGraphQLError(
        [
            {
                "message": "Couldn't find LlmProvider with id bogus",
                "extensions": {"code": "RESOURCE_NOT_FOUND"},
            }
        ]
    )


WRITTEN_PROVIDER = {
    "id": "42",
    "name": "My OpenAI",
    "type": "byom",
    "active": True,
    "organizationDefault": False,
}


@pytest.fixture
def mock_provider_client():
    client = MagicMock(PipefyClient)
    client.get_llm_providers = AsyncMock()
    client.get_available_ai_models = AsyncMock()
    client.get_default_llm_provider = AsyncMock()
    client.get_llm_provider_dependencies = AsyncMock()
    client.validate_llm_provider_access = AsyncMock()
    client.create_llm_provider = AsyncMock()
    client.update_llm_provider = AsyncMock()
    client.delete_llm_provider = AsyncMock()
    client.set_llm_provider_active_status = AsyncMock()
    client.set_default_llm_provider = AsyncMock()
    client.reset_default_llm_provider = AsyncMock()
    return client


@pytest.fixture
def provider_mcp_server(mock_provider_client):
    return build_tool_test_server(
        "Pipefy LLM Provider Tools Test",
        LlmProviderTools.register,
        mock_provider_client,
    )


@pytest.fixture
def provider_session(provider_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        provider_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
async def test_get_llm_providers_success_with_pagination(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.get_llm_providers = AsyncMock(
        return_value={
            "providers": [SYSTEM_NODE, BYOM_NODE],
            "page_info": {"hasNextPage": True, "endCursor": "c1"},
        }
    )
    async with provider_session as session:
        result = await session.call_tool(
            "get_llm_providers", {"organization_uuid": "org-uuid-1", "first": 2}
        )
    assert result.is_error is False
    mock_provider_client.get_llm_providers.assert_awaited_once_with(
        "org-uuid-1", only_active=False, first=2, after=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert [p["type"] for p in payload["data"]["providers"]] == ["system", "byom"]
    assert payload["pagination"] == {
        "has_more": True,
        "end_cursor": "c1",
        "page_size": 2,
    }


@pytest.mark.anyio
async def test_get_llm_providers_blank_org_uuid_rejected(
    provider_session, mock_provider_client, extract_payload
):
    async with provider_session as session:
        result = await session.call_tool(
            "get_llm_providers", {"organization_uuid": "   "}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "organization_uuid" in tool_error_message(payload)
    mock_provider_client.get_llm_providers.assert_not_awaited()


@pytest.mark.anyio
async def test_get_llm_providers_invalid_page_size_rejected(
    provider_session, mock_provider_client, extract_payload
):
    async with provider_session as session:
        result = await session.call_tool(
            "get_llm_providers", {"organization_uuid": "org-uuid-1", "first": 0}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"


@pytest.mark.anyio
async def test_get_llm_providers_permission_denied_classified(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.get_llm_providers = AsyncMock(
        side_effect=permission_denied_error()
    )
    async with provider_session as session:
        result = await session.call_tool(
            "get_llm_providers", {"organization_uuid": "org-uuid-1"}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "PERMISSION_DENIED"
    assert payload["error"]["details"]["kind"] == "permission_denied"
    assert payload["error"]["details"]["correlation_id"] == "corr-9"


@pytest.mark.anyio
async def test_get_available_ai_models_success(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.get_available_ai_models = AsyncMock(
        return_value=["gpt-4o", "gpt-4o-mini"]
    )
    async with provider_session as session:
        result = await session.call_tool(
            "get_available_ai_models", {"provider_name": "openai"}
        )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["models"] == ["gpt-4o", "gpt-4o-mini"]
    mock_provider_client.get_available_ai_models.assert_awaited_once_with("openai")


@pytest.mark.anyio
async def test_get_available_ai_models_invalid_enum_surfaces_api_error(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.get_available_ai_models = AsyncMock(
        side_effect=PipefyGraphQLError(
            [
                {
                    "message": "Invalid provider name",
                    "extensions": {"code": "INVALID_ARGUMENTS"},
                }
            ]
        )
    )
    async with provider_session as session:
        result = await session.call_tool(
            "get_available_ai_models", {"provider_name": "bogus"}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["details"]["kind"] == "invalid_arguments"


@pytest.mark.anyio
async def test_get_default_llm_provider_defaults_to_organization(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.get_default_llm_provider = AsyncMock(return_value=BYOM_NODE)
    async with provider_session as session:
        result = await session.call_tool(
            "get_default_llm_provider", {"owner_id": "123456"}
        )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["provider"]["id"] == "42"
    mock_provider_client.get_default_llm_provider.assert_awaited_once_with(
        "123456", owner_type="organization"
    )


@pytest.mark.anyio
async def test_get_llm_provider_dependencies_success(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.get_llm_provider_dependencies = AsyncMock(
        return_value={
            "dependencies": [{"ownerId": "1", "ownerType": "organization"}],
            "page_info": {"hasNextPage": False, "endCursor": None},
            "total_count": 1,
        }
    )
    async with provider_session as session:
        result = await session.call_tool(
            "get_llm_provider_dependencies",
            {"provider_id": "42", "organization_uuid": "org-uuid-1"},
        )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["total_count"] == 1
    assert payload["data"]["dependencies"][0]["ownerType"] == "organization"
    assert payload["pagination"]["has_more"] is False


@pytest.mark.anyio
async def test_validate_llm_provider_access_green(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.validate_llm_provider_access = AsyncMock(
        return_value={
            "ok": True,
            "system_providers_visible": True,
            "custom_providers_visible": False,
            "provider_count": 3,
            "note": "Read access confirmed. This proves list/read access only...",
        }
    )
    async with provider_session as session:
        result = await session.call_tool(
            "validate_llm_provider_access", {"organization_uuid": "org-uuid-1"}
        )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["ok"] is True
    assert payload["data"]["system_providers_visible"] is True


@pytest.mark.anyio
async def test_validate_llm_provider_access_failure_maps_problem(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.validate_llm_provider_access = AsyncMock(
        return_value={
            "ok": False,
            "problem": {
                "kind": "permission_denied",
                "message": "Permission denied",
                "code": "PERMISSION_DENIED",
                "correlation_id": "corr-2",
            },
        }
    )
    async with provider_session as session:
        result = await session.call_tool(
            "validate_llm_provider_access", {"organization_uuid": "org-uuid-1"}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "PERMISSION_DENIED"
    assert payload["error"]["details"]["kind"] == "permission_denied"
    assert payload["error"]["details"]["correlation_id"] == "corr-2"


@pytest.mark.anyio
async def test_get_llm_providers_not_found_has_no_self_referential_hint(
    provider_session, mock_provider_client, extract_payload
):
    """A failed list must not tell the caller to retry the list tool itself."""
    mock_provider_client.get_llm_providers = AsyncMock(side_effect=not_found_error())
    async with provider_session as session:
        result = await session.call_tool(
            "get_llm_providers", {"organization_uuid": "org-uuid-1"}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["details"]["kind"] == "not_found"
    assert "get_llm_providers" not in tool_error_message(payload)


@pytest.mark.anyio
async def test_get_llm_provider_dependencies_not_found_adds_discovery_hint(
    provider_session, mock_provider_client, extract_payload
):
    """A per-id tool keeps the discovery hint so the caller can find valid IDs."""
    mock_provider_client.get_llm_provider_dependencies = AsyncMock(
        side_effect=not_found_error()
    )
    async with provider_session as session:
        result = await session.call_tool(
            "get_llm_provider_dependencies",
            {"provider_id": "bogus", "organization_uuid": "org-uuid-1"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["details"]["kind"] == "not_found"
    assert "get_llm_providers" in tool_error_message(payload)


@pytest.mark.anyio
async def test_transport_failure_without_graphql_errors_falls_back_to_str(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.get_llm_providers = AsyncMock(
        side_effect=RuntimeError("socket closed")
    )
    async with provider_session as session:
        result = await session.call_tool(
            "get_llm_providers", {"organization_uuid": "org-uuid-1"}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "socket closed" in tool_error_message(payload)


# --- Write tools ---------------------------------------------------------


@pytest.mark.anyio
async def test_create_and_update_take_file_path_not_inline_configuration(
    provider_session,
):
    """Secrets can only arrive via a file path: no inline `configuration` input."""
    async with provider_session as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
    for name in ("create_llm_provider", "update_llm_provider"):
        props = tools[name].input_schema.get("properties", {})
        assert "configuration_file_path" in props
        assert "configuration" not in props


@pytest.mark.anyio
async def test_create_llm_provider_success_returns_no_configuration(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.create_llm_provider = AsyncMock(return_value=WRITTEN_PROVIDER)
    async with provider_session as session:
        result = await session.call_tool(
            "create_llm_provider",
            {
                "organization_uuid": "org-uuid-1",
                "name": "My OpenAI",
                "configuration_file_path": "/tmp/config.json",
            },
        )
    assert result.is_error is False
    mock_provider_client.create_llm_provider.assert_awaited_once_with(
        "org-uuid-1", name="My OpenAI", configuration_file_path="/tmp/config.json"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    # The response must never carry configuration.
    assert "configuration" not in str(payload)


@pytest.mark.anyio
async def test_create_llm_provider_value_error_becomes_tool_error(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.create_llm_provider = AsyncMock(
        side_effect=ValueError(
            "Provider configuration must be a non-empty JSON object."
        )
    )
    async with provider_session as session:
        result = await session.call_tool(
            "create_llm_provider",
            {
                "organization_uuid": "org-uuid-1",
                "name": "X",
                "configuration_file_path": "/tmp/bad.json",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "non-empty JSON object" in tool_error_message(payload)


@pytest.mark.anyio
async def test_update_llm_provider_success(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.update_llm_provider = AsyncMock(return_value=WRITTEN_PROVIDER)
    async with provider_session as session:
        result = await session.call_tool(
            "update_llm_provider",
            {
                "provider_id": "42",
                "organization_uuid": "org-uuid-1",
                "configuration_file_path": "/tmp/config.json",
                "name": "Renamed",
            },
        )
    assert result.is_error is False
    mock_provider_client.update_llm_provider.assert_awaited_once_with(
        "42",
        "org-uuid-1",
        configuration_file_path="/tmp/config.json",
        name="Renamed",
    )
    assert "configuration" not in str(extract_payload(result))


@pytest.mark.anyio
async def test_delete_preview_without_confirm_does_not_delete(
    provider_session, mock_provider_client, extract_payload
):
    async with provider_session as session:
        result = await session.call_tool(
            "delete_llm_provider",
            {"provider_id": "42", "organization_uuid": "org-uuid-1"},
        )
    payload = extract_payload(result)
    assert payload["requires_confirmation"] is True
    mock_provider_client.delete_llm_provider.assert_not_awaited()


@pytest.mark.anyio
async def test_delete_with_confirm_executes(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.delete_llm_provider = AsyncMock(return_value={"success": True})
    async with provider_session as session:
        result = await session.call_tool(
            "delete_llm_provider",
            {"provider_id": "42", "organization_uuid": "org-uuid-1", "confirm": True},
        )
    assert result.is_error is False
    mock_provider_client.delete_llm_provider.assert_awaited_once_with(
        "42", "org-uuid-1"
    )
    assert extract_payload(result)["data"]["deleted_id"] == "42"


@pytest.mark.anyio
async def test_delete_unconfirmed_by_api_is_tool_error(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.delete_llm_provider = AsyncMock(
        return_value={"success": False}
    )
    async with provider_session as session:
        result = await session.call_tool(
            "delete_llm_provider",
            {"provider_id": "42", "organization_uuid": "org-uuid-1", "confirm": True},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "did not confirm" in tool_error_message(payload)


@pytest.mark.anyio
async def test_set_active_status_success(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.set_llm_provider_active_status = AsyncMock(
        return_value={"success": True}
    )
    async with provider_session as session:
        result = await session.call_tool(
            "set_llm_provider_active_status", {"provider_id": "42", "active": False}
        )
    assert result.is_error is False
    mock_provider_client.set_llm_provider_active_status.assert_awaited_once_with(
        "42", active=False
    )
    data = extract_payload(result)["data"]
    assert data == {"provider_id": "42", "active": False}


@pytest.mark.anyio
async def test_set_default_success(
    provider_session, mock_provider_client, extract_payload
):
    active = {"id": "a1", "llmProviderId": "42"}
    mock_provider_client.set_default_llm_provider = AsyncMock(return_value=active)
    async with provider_session as session:
        result = await session.call_tool(
            "set_default_llm_provider",
            {"organization_id": "123456", "provider_id": "42"},
        )
    assert result.is_error is False
    mock_provider_client.set_default_llm_provider.assert_awaited_once_with(
        "123456", provider_id="42", system_provider_id=None
    )
    assert extract_payload(result)["data"]["active_provider"] == active


@pytest.mark.anyio
async def test_set_default_xor_violation_is_tool_error(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.set_default_llm_provider = AsyncMock(
        side_effect=ValueError(
            "Provide exactly one of provider_id or system_provider_id."
        )
    )
    async with provider_session as session:
        result = await session.call_tool(
            "set_default_llm_provider",
            {
                "organization_id": "123456",
                "provider_id": "42",
                "system_provider_id": "7",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "exactly one" in tool_error_message(payload)


@pytest.mark.anyio
async def test_reset_default_success(
    provider_session, mock_provider_client, extract_payload
):
    mock_provider_client.reset_default_llm_provider = AsyncMock(
        return_value={"success": True}
    )
    async with provider_session as session:
        result = await session.call_tool(
            "reset_default_llm_provider", {"organization_id": "123456"}
        )
    assert result.is_error is False
    mock_provider_client.reset_default_llm_provider.assert_awaited_once_with("123456")
    assert extract_payload(result)["data"]["organization_id"] == "123456"
