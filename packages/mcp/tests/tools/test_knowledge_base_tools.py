"""Tests for AI knowledge base MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import (
    KnowledgeBaseDocumentUploadError,
    PipefyClient,
    PipefyGraphQLError,
)

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

DOCUMENT_FULL = {
    "id": "kb-2",
    "name": "Handbook",
    "description": "Company handbook",
    "content": "https://app.pipefy.com/storage/v1/signed/orgs/o/u/h.pdf?sig=x",
    "updatedAt": "2026-07-16T00:00:00Z",
}

DATA_LOOKUP_FULL = {
    "id": "kb-3",
    "name": "Order lookup",
    "description": "Find orders by customer email",
    "sourceRepoId": "303088927",
    "searchQuery": None,
    "outputFields": ["title", "status"],
    "updatedAt": "2026-07-18T00:00:00Z",
}

STATIC_CONDITION = {"field": "title", "operator": "contains", "value": "urgent"}


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
                "message": "Couldn't find Pipe with uuid bogus",
                "extensions": {"code": "RESOURCE_NOT_FOUND"},
            }
        ]
    )


@pytest.fixture
def mock_kb_client():
    client = MagicMock(PipefyClient)
    client.get_ai_knowledge_bases = AsyncMock()
    client.get_ai_knowledge_base_plain_text = AsyncMock()
    client.create_ai_knowledge_base_plain_text = AsyncMock()
    client.update_ai_knowledge_base_plain_text = AsyncMock()
    client.delete_ai_knowledge_base_plain_text = AsyncMock()
    client.get_ai_knowledge_base_document = AsyncMock()
    client.create_ai_knowledge_base_document = AsyncMock()
    client.update_ai_knowledge_base_document = AsyncMock()
    client.delete_ai_knowledge_base_document = AsyncMock()
    client.get_ai_knowledge_base_data_lookup = AsyncMock()
    client.create_ai_knowledge_base_data_lookup = AsyncMock()
    client.update_ai_knowledge_base_data_lookup = AsyncMock()
    client.delete_ai_knowledge_base_data_lookup = AsyncMock()
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
async def test_get_knowledge_bases_success(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.get_ai_knowledge_bases = AsyncMock(return_value=[PLAIN_TEXT_NODE])
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_bases", {"pipe_uuid": "pipe-uuid-1"}
        )
    assert result.is_error is False
    mock_kb_client.get_ai_knowledge_bases.assert_awaited_once_with("pipe-uuid-1")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["knowledge_bases"] == [PLAIN_TEXT_NODE]


@pytest.mark.anyio
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
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["knowledge_base_plain_text"] == PLAIN_TEXT_FULL


@pytest.mark.anyio
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
    assert result.is_error is False
    mock_kb_client.update_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "kb-1", "pipe-uuid-1", name=None, content="New content", description=None
    )


@pytest.mark.anyio
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
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_kb_client.delete_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "kb-1", "pipe-uuid-1"
    )


@pytest.mark.anyio
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
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["knowledge_base_count"] == 2


@pytest.mark.anyio
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


@pytest.mark.anyio
async def test_get_knowledge_bases_not_found_has_no_self_referential_hint(
    kb_session, mock_kb_client, extract_payload
):
    """A failed list must not tell the caller to retry the list tool itself."""
    mock_kb_client.get_ai_knowledge_bases = AsyncMock(side_effect=not_found_error())
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_bases", {"pipe_uuid": "bogus"}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["details"]["kind"] == "not_found"
    assert "get_ai_knowledge_bases" not in tool_error_message(payload)


async def test_get_document_success(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.get_ai_knowledge_base_document = AsyncMock(
        return_value=DOCUMENT_FULL
    )
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_base_document",
            {"document_id": "kb-2", "pipe_uuid": "pipe-uuid-1"},
        )
    assert result.is_error is False
    mock_kb_client.get_ai_knowledge_base_document.assert_awaited_once_with(
        "kb-2", "pipe-uuid-1"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["knowledge_base_document"] == DOCUMENT_FULL


@pytest.mark.anyio
async def test_get_document_not_found(kb_session, mock_kb_client, extract_payload):
    mock_kb_client.get_ai_knowledge_base_document = AsyncMock(return_value={})
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_base_document",
            {"document_id": "kb-x", "pipe_uuid": "pipe-uuid-1"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_create_document_success(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.create_ai_knowledge_base_document = AsyncMock(
        return_value=DOCUMENT_FULL
    )
    async with kb_session as session:
        result = await session.call_tool(
            "create_ai_knowledge_base_document",
            {
                "pipe_uuid": "pipe-uuid-1",
                "name": "Handbook",
                "description": "Company handbook",
                "file_path": "/tmp/handbook.pdf",
            },
        )
    assert result.is_error is False
    mock_kb_client.create_ai_knowledge_base_document.assert_awaited_once_with(
        "pipe-uuid-1",
        name="Handbook",
        description="Company handbook",
        file_path="/tmp/handbook.pdf",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["knowledge_base_document"] == DOCUMENT_FULL


@pytest.mark.anyio
async def test_create_document_blank_file_path_rejected(
    kb_session, mock_kb_client, extract_payload
):
    async with kb_session as session:
        result = await session.call_tool(
            "create_ai_knowledge_base_document",
            {
                "pipe_uuid": "pipe-uuid-1",
                "name": "Handbook",
                "description": "d",
                "file_path": "   ",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "file_path" in tool_error_message(payload)
    mock_kb_client.create_ai_knowledge_base_document.assert_not_awaited()


@pytest.mark.anyio
async def test_create_document_non_pdf_maps_file_read_step(
    kb_session, mock_kb_client, extract_payload
):
    mock_kb_client.create_ai_knowledge_base_document = AsyncMock(
        side_effect=KnowledgeBaseDocumentUploadError(
            "File must be a .pdf: notes.txt", step="file_read"
        )
    )
    async with kb_session as session:
        result = await session.call_tool(
            "create_ai_knowledge_base_document",
            {
                "pipe_uuid": "pipe-uuid-1",
                "name": "n",
                "description": "d",
                "file_path": "/tmp/notes.txt",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert ".pdf" in tool_error_message(payload)
    assert payload["error"]["details"]["step"] == "file_read"


@pytest.mark.anyio
async def test_create_document_s3_failure_carries_step_and_snippet(
    kb_session, mock_kb_client, extract_payload
):
    mock_kb_client.create_ai_knowledge_base_document = AsyncMock(
        side_effect=KnowledgeBaseDocumentUploadError(
            "S3 upload failed with HTTP 403.",
            step="s3_upload",
            body_snippet="AccessDenied",
            status_code=403,
        )
    )
    async with kb_session as session:
        result = await session.call_tool(
            "create_ai_knowledge_base_document",
            {
                "pipe_uuid": "pipe-uuid-1",
                "name": "n",
                "description": "d",
                "file_path": "/tmp/handbook.pdf",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["details"]["step"] == "s3_upload"
    assert payload["error"]["details"]["body_snippet"] == "AccessDenied"


@pytest.mark.anyio
async def test_create_document_kb_create_failure_classified(
    kb_session, mock_kb_client, extract_payload
):
    mock_kb_client.create_ai_knowledge_base_document = AsyncMock(
        side_effect=KnowledgeBaseDocumentUploadError(
            "Document create failed: denied",
            step="kb_create",
        )
    )
    mock_kb_client.create_ai_knowledge_base_document.side_effect.__cause__ = (
        permission_denied_error()
    )
    async with kb_session as session:
        result = await session.call_tool(
            "create_ai_knowledge_base_document",
            {
                "pipe_uuid": "pipe-uuid-1",
                "name": "n",
                "description": "d",
                "file_path": "/tmp/handbook.pdf",
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["error"]["details"]["step"] == "kb_create"
    assert payload["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.anyio
async def test_update_document_success(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.update_ai_knowledge_base_document = AsyncMock(
        return_value=DOCUMENT_FULL
    )
    async with kb_session as session:
        result = await session.call_tool(
            "update_ai_knowledge_base_document",
            {"document_id": "kb-2", "pipe_uuid": "pipe-uuid-1", "name": "New name"},
        )
    assert result.is_error is False
    mock_kb_client.update_ai_knowledge_base_document.assert_awaited_once_with(
        "kb-2", "pipe-uuid-1", name="New name", description=None
    )


@pytest.mark.anyio
async def test_delete_document_preview_without_confirm(
    kb_session, mock_kb_client, extract_payload
):
    async with kb_session as session:
        result = await session.call_tool(
            "delete_ai_knowledge_base_document",
            {"document_id": "kb-2", "pipe_uuid": "pipe-uuid-1"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    mock_kb_client.delete_ai_knowledge_base_document.assert_not_awaited()


@pytest.mark.anyio
async def test_delete_document_with_confirm_executes(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.delete_ai_knowledge_base_document = AsyncMock(
        return_value={"success": True, "errors": []}
    )
    async with kb_session as session:
        result = await session.call_tool(
            "delete_ai_knowledge_base_document",
            {"document_id": "kb-2", "pipe_uuid": "pipe-uuid-1", "confirm": True},
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_kb_client.delete_ai_knowledge_base_document.assert_awaited_once_with(
        "kb-2", "pipe-uuid-1"
    )


@pytest.mark.anyio
async def test_get_data_lookup_success(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.get_ai_knowledge_base_data_lookup = AsyncMock(
        return_value=DATA_LOOKUP_FULL
    )
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_base_data_lookup",
            {"data_lookup_id": "kb-3", "pipe_uuid": "pipe-uuid-1"},
        )
    assert result.is_error is False
    mock_kb_client.get_ai_knowledge_base_data_lookup.assert_awaited_once_with(
        "kb-3", "pipe-uuid-1"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["knowledge_base_data_lookup"] == DATA_LOOKUP_FULL


@pytest.mark.anyio
async def test_get_data_lookup_not_found(kb_session, mock_kb_client, extract_payload):
    mock_kb_client.get_ai_knowledge_base_data_lookup = AsyncMock(return_value={})
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_base_data_lookup",
            {"data_lookup_id": "kb-x", "pipe_uuid": "pipe-uuid-1"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload)
    assert "not found" in message.lower()
    assert "get_ai_knowledge_bases" in message


@pytest.mark.anyio
async def test_create_data_lookup_success(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.create_ai_knowledge_base_data_lookup = AsyncMock(
        return_value=DATA_LOOKUP_FULL
    )
    async with kb_session as session:
        result = await session.call_tool(
            "create_ai_knowledge_base_data_lookup",
            {
                "pipe_uuid": "pipe-uuid-1",
                "name": "Order lookup",
                "description": "Find orders",
                "source_repo_id": "303088927",
                "output_fields": ["title"],
                "conditions": [STATIC_CONDITION],
            },
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["knowledge_base_data_lookup"] == DATA_LOOKUP_FULL
    mock_kb_client.create_ai_knowledge_base_data_lookup.assert_awaited_once_with(
        "pipe-uuid-1",
        name="Order lookup",
        description="Find orders",
        source_repo_id="303088927",
        output_fields=["title"],
        conditions=[STATIC_CONDITION],
        search_query=None,
    )


@pytest.mark.anyio
async def test_create_data_lookup_definition_value_error_mapped(
    kb_session, mock_kb_client, extract_payload
):
    mock_kb_client.create_ai_knowledge_base_data_lookup = AsyncMock(
        side_effect=ValueError(
            "source_repo_id must be the numeric pipe ID (a pipe UUID is "
            "accepted by the API but breaks the lookup when an agent runs it)"
        )
    )
    async with kb_session as session:
        result = await session.call_tool(
            "create_ai_knowledge_base_data_lookup",
            {
                "pipe_uuid": "pipe-uuid-1",
                "name": "Order lookup",
                "description": "Find orders",
                "source_repo_id": "5f66417e-5adc-4c83-908f-0b888493c847",
                "output_fields": ["title"],
                "conditions": [STATIC_CONDITION],
            },
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "numeric pipe ID" in tool_error_message(payload)


@pytest.mark.anyio
async def test_update_data_lookup_success(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.update_ai_knowledge_base_data_lookup = AsyncMock(
        return_value=DATA_LOOKUP_FULL
    )
    async with kb_session as session:
        result = await session.call_tool(
            "update_ai_knowledge_base_data_lookup",
            {
                "data_lookup_id": "kb-3",
                "pipe_uuid": "pipe-uuid-1",
                "source_repo_id": "303088927",
                "output_fields": ["title"],
                "conditions": [STATIC_CONDITION],
                "name": "Renamed",
            },
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_kb_client.update_ai_knowledge_base_data_lookup.assert_awaited_once_with(
        "kb-3",
        "pipe-uuid-1",
        source_repo_id="303088927",
        output_fields=["title"],
        conditions=[STATIC_CONDITION],
        search_query=None,
        name="Renamed",
        description=None,
    )


@pytest.mark.anyio
async def test_update_data_lookup_requires_full_definition_in_schema(kb_session):
    """The tool schema itself enforces the full-definition contract."""
    async with kb_session as session:
        tools = await session.list_tools()
    tool = next(
        t for t in tools.tools if t.name == "update_ai_knowledge_base_data_lookup"
    )
    assert set(tool.input_schema["required"]) >= {
        "data_lookup_id",
        "pipe_uuid",
        "source_repo_id",
        "output_fields",
        "conditions",
    }


@pytest.mark.anyio
async def test_delete_data_lookup_preview_without_confirm(
    kb_session, mock_kb_client, extract_payload
):
    async with kb_session as session:
        result = await session.call_tool(
            "delete_ai_knowledge_base_data_lookup",
            {"data_lookup_id": "kb-3", "pipe_uuid": "pipe-uuid-1"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    mock_kb_client.delete_ai_knowledge_base_data_lookup.assert_not_awaited()


@pytest.mark.anyio
async def test_delete_data_lookup_with_confirm_executes(
    kb_session, mock_kb_client, unified_envelope, extract_payload
):
    mock_kb_client.delete_ai_knowledge_base_data_lookup = AsyncMock(
        return_value={"success": True, "errors": []}
    )
    async with kb_session as session:
        result = await session.call_tool(
            "delete_ai_knowledge_base_data_lookup",
            {"data_lookup_id": "kb-3", "pipe_uuid": "pipe-uuid-1", "confirm": True},
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is True
    mock_kb_client.delete_ai_knowledge_base_data_lookup.assert_awaited_once_with(
        "kb-3", "pipe-uuid-1"
    )


@pytest.mark.anyio
async def test_get_data_lookup_permission_denied_classified(
    kb_session, mock_kb_client, extract_payload
):
    mock_kb_client.get_ai_knowledge_base_data_lookup = AsyncMock(
        side_effect=permission_denied_error()
    )
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_base_data_lookup",
            {"data_lookup_id": "kb-3", "pipe_uuid": "pipe-uuid-1"},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    error = payload.get("error") or {}
    details = error.get("details") or {}
    assert details.get("kind") == "permission_denied"


@pytest.mark.anyio
@pytest.mark.parametrize("exc_message", ["", "   "])
async def test_empty_exception_message_uses_fallback(
    kb_session, mock_kb_client, extract_payload, exc_message
):
    mock_kb_client.get_ai_knowledge_bases = AsyncMock(
        side_effect=RuntimeError(exc_message)
    )
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_bases", {"pipe_uuid": "pipe-uuid-1"}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload)
    assert message.strip()
    assert "Knowledge base request failed." in message
    assert "do not blind-retry" in message


@pytest.mark.anyio
@pytest.mark.parametrize("exc_message", ["", "   "])
async def test_classified_whitespace_permission_denied_keeps_unknown_error(
    kb_session, mock_kb_client, extract_payload, exc_message
):
    mock_kb_client.get_ai_knowledge_bases = AsyncMock(
        side_effect=PipefyGraphQLError(
            [
                {
                    "message": exc_message,
                    "extensions": {
                        "code": "PERMISSION_DENIED",
                        "correlation_id": "corr-ws",
                    },
                }
            ]
        )
    )
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_bases", {"pipe_uuid": "pipe-uuid-1"}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert tool_error_message(payload) == "Unknown error"
    assert payload["error"]["code"] == "PERMISSION_DENIED"
    assert payload["error"]["details"]["kind"] == "permission_denied"
    assert "do not blind-retry" not in tool_error_message(payload)


@pytest.mark.anyio
async def test_non_empty_exception_message_preserved(
    kb_session, mock_kb_client, extract_payload
):
    mock_kb_client.get_ai_knowledge_bases = AsyncMock(
        side_effect=RuntimeError("socket closed")
    )
    async with kb_session as session:
        result = await session.call_tool(
            "get_ai_knowledge_bases", {"pipe_uuid": "pipe-uuid-1"}
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "socket closed" in tool_error_message(payload)
