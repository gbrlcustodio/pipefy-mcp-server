"""Tests for AI knowledge base MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient

from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.knowledge_base_tools import KnowledgeBaseTools
from tools.conftest import build_tool_test_server

PLAIN_TEXT_NODE = {
    "id": "kb-1",
    "type": "knowledge_base_plain_texts",
    "name": "Onboarding",
    "description": "How to onboard",
    "updatedAt": "2026-07-17T00:00:00Z",
}

PLAIN_TEXT_FULL = {
    "id": "kb-1",
    "name": "Onboarding",
    "description": "How to onboard",
    "content": "Step 1...",
    "updatedAt": "2026-07-17T00:00:00Z",
}


def permission_denied_error() -> TransportQueryError:
    return TransportQueryError(
        "denied",
        errors=[
            {
                "message": "Permission denied",
                "extensions": {"code": "PERMISSION_DENIED", "correlation_id": "corr-9"},
            }
        ],
    )


def not_found_error() -> TransportQueryError:
    return TransportQueryError(
        "missing",
        errors=[
            {
                "message": "Couldn't find Pipe with uuid bogus",
                "extensions": {"code": "RESOURCE_NOT_FOUND"},
            }
        ],
    )


@pytest.fixture
def mock_kb_client():
    client = MagicMock(PipefyClient)
    client.get_ai_knowledge_bases = AsyncMock()
    client.get_ai_knowledge_base_plain_text = AsyncMock()
    client.create_ai_knowledge_base_plain_text = AsyncMock()
    client.update_ai_knowledge_base_plain_text = AsyncMock()
    client.delete_ai_knowledge_base_plain_text = AsyncMock()
    client.validate_knowledge_base_access = AsyncMock()
    return client


@pytest.fixture
def kb_mcp_server(mock_kb_client):
    return build_tool_test_server(
        "Pipefy Knowledge Base Tools Test",
        KnowledgeBaseTools.register,
        mock_kb_client,
    )


@pytest.fixture
def kb_session(kb_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        kb_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_get_knowledge_bases_success(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.get_ai_knowledge_bases = AsyncMock(return_value=[PLAIN_TEXT_NODE])
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_bases", {"pipe_uuid": "pipe-uuid-1"}
        )
    assert result.isError is False
    mock_kb_client.get_ai_knowledge_bases.assert_awaited_once_with("pipe-uuid-1")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["knowledge_bases"] == [PLAIN_TEXT_NODE]


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_get_knowledge_bases_blank_pipe_uuid_rejected(
    kb_session, mock_kb_client, extract_payload
):
    async with kb_session as session:
        result = await session.call_tool("get_ai_knowledge_bases", {"pipe_uuid": "   "})
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "pipe_uuid" in tool_error_message(payload)
    mock_kb_client.get_ai_knowledge_bases.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_get_plain_text_not_found(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.get_ai_knowledge_base_plain_text = AsyncMock(return_value={})
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_base_plain_text",
            {"plain_text_id": "kb-x", "pipe_uuid": "pipe-uuid-1"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_create_plain_text_success(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.create_ai_knowledge_base_plain_text = AsyncMock(
        return_value=PLAIN_TEXT_FULL
    )
    async with kb_session as session:
        result = await session.call_tool(
            "create_ai_knowledge_base_plain_text",
            {
                "pipe_uuid": "pipe-uuid-1",
                "name": "Onboarding",
                "content": "Step 1...",
                "description": "How to onboard",
            },
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["knowledge_base_plain_text"] == PLAIN_TEXT_FULL


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_create_plain_text_limit_value_error_mapped(
    kb_session, mock_kb_client, extract_payload
):
    mock_kb_client.create_ai_knowledge_base_plain_text = AsyncMock(
        side_effect=ValueError("content must be at most 3500 characters (got 3501)")
    )
    async with kb_session as session:
        result = await session.call_tool(
            "create_ai_knowledge_base_plain_text",
            {
                "pipe_uuid": "pipe-uuid-1",
                "name": "n",
                "content": "x",
                "description": "d",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "3500" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_update_plain_text_success(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.update_ai_knowledge_base_plain_text = AsyncMock(
        return_value=PLAIN_TEXT_FULL
    )
    async with kb_session as session:
        result = await session.call_tool(
            "update_ai_knowledge_base_plain_text",
            {
                "plain_text_id": "kb-1",
                "pipe_uuid": "pipe-uuid-1",
                "content": "New content",
            },
        )
    assert result.isError is False
    mock_kb_client.update_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "kb-1", "pipe-uuid-1", name=None, content="New content", description=None
    )


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_delete_preview_without_confirm_does_not_delete(
    kb_session, mock_kb_client, extract_payload
):
    async with kb_session as session:
        result = await session.call_tool(
            "delete_ai_knowledge_base_plain_text",
            {"plain_text_id": "kb-1", "pipe_uuid": "pipe-uuid-1"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    mock_kb_client.delete_ai_knowledge_base_plain_text.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_delete_with_confirm_executes(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.delete_ai_knowledge_base_plain_text = AsyncMock(
        return_value={"success": True, "errors": []}
    )
    async with kb_session as session:
        result = await session.call_tool(
            "delete_ai_knowledge_base_plain_text",
            {"plain_text_id": "kb-1", "pipe_uuid": "pipe-uuid-1", "confirm": True},
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_kb_client.delete_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "kb-1", "pipe-uuid-1"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_validate_access_green(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.validate_knowledge_base_access = AsyncMock(
        return_value={
            "ok": True,
            "knowledge_base_count": 2,
            "note": "Read access confirmed.",
        }
    )
    async with kb_session as session:
        result = await session.call_tool(
            "validate_knowledge_base_access", {"pipe_uuid": "pipe-uuid-1"}
        )
    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["knowledge_base_count"] == 2


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_validate_access_failure_classified(
    kb_session, mock_kb_client, extract_payload
):
    mock_kb_client.validate_knowledge_base_access = AsyncMock(
        return_value={
            "ok": False,
            "problem": {
                "kind": "permission_denied",
                "message": "Permission denied",
                "code": "PERMISSION_DENIED",
                "correlation_id": "corr-9",
            },
        }
    )
    async with kb_session as session:
        result = await session.call_tool(
            "validate_knowledge_base_access", {"pipe_uuid": "pipe-uuid-1"}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "PERMISSION_DENIED"
    assert payload["error"]["details"]["kind"] == "permission_denied"
    assert payload["error"]["details"]["correlation_id"] == "corr-9"


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_get_knowledge_bases_permission_denied_classified(
    kb_session, mock_kb_client, extract_payload
):
    mock_kb_client.get_ai_knowledge_bases = AsyncMock(
        side_effect=permission_denied_error()
    )
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_bases", {"pipe_uuid": "pipe-uuid-1"}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["code"] == "PERMISSION_DENIED"
    assert payload["error"]["details"]["correlation_id"] == "corr-9"


@pytest.mark.anyio
@pytest.mark.parametrize("kb_session", [None], indirect=True)
async def test_get_plain_text_not_found_error_adds_discovery_hint(
    kb_session, mock_kb_client, extract_payload
):
    mock_kb_client.get_ai_knowledge_base_plain_text = AsyncMock(
        side_effect=not_found_error()
    )
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_base_plain_text",
            {"plain_text_id": "kb-x", "pipe_uuid": "pipe-uuid-1"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["details"]["kind"] == "not_found"
    assert "get_ai_knowledge_bases" in tool_error_message(payload)
