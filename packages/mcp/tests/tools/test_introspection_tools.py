"""Tests for GraphQL introspection MCP tools (mocked PipefyClient)."""

import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from pipefy_sdk import PipefyClient, PipefyGraphQLError

from pipefy_mcp.core.tool_error_envelope import tool_error_message
from pipefy_mcp.tools.introspection_tools import IntrospectionTools
from tools.conftest import build_tool_test_server
from tools.destructive_confirm_test_support import confirm_after_preview


@pytest.fixture
def mock_introspection_client():
    client = MagicMock(PipefyClient)
    client.introspect_type = AsyncMock()
    client.introspect_mutation = AsyncMock()
    client.introspect_query = AsyncMock()
    client.search_schema = AsyncMock()
    client.execute_graphql = AsyncMock()
    return client


@pytest.fixture
def introspection_mcp_server(mock_introspection_client):
    return build_tool_test_server(
        "Pipefy Introspection Tools Test",
        IntrospectionTools.register,
        mock_introspection_client,
    )


@pytest.fixture
def introspection_session(introspection_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        introspection_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
async def test_introspect_type_success(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_type = AsyncMock(
        return_value={"name": "Card", "kind": "OBJECT", "fields": []}
    )
    async with introspection_session as session:
        result = await session.call_tool("introspect_type", {"type_name": "Card"})
    assert result.is_error is False
    mock_introspection_client.introspect_type.assert_awaited_once_with(
        "Card", max_depth=1
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "Card" in payload["result"]
    assert "OBJECT" in payload["result"]


@pytest.mark.anyio
async def test_introspect_type_with_max_depth_passes_through(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_type = AsyncMock(
        return_value={"name": "Card", "kind": "OBJECT", "fields": []}
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "introspect_type", {"type_name": "Card", "max_depth": 2}
        )
    assert result.is_error is False
    mock_introspection_client.introspect_type.assert_awaited_once_with(
        "Card", max_depth=2
    )


@pytest.mark.anyio
async def test_introspect_type_not_found_returns_error_payload(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_type = AsyncMock(
        return_value={"error": "GraphQL type 'Nope' was not found."}
    )
    async with introspection_session as session:
        result = await session.call_tool("introspect_type", {"type_name": "Nope"})
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_introspect_type_transport_error_returns_structured_error(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_type = AsyncMock(
        side_effect=PipefyGraphQLError([{"message": "timeout"}])
    )
    async with introspection_session as session:
        result = await session.call_tool("introspect_type", {"type_name": "Card"})
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert isinstance(payload.get("error"), dict)
    assert "message" in payload["error"]


@pytest.mark.anyio
async def test_introspect_mutation_success(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_mutation = AsyncMock(
        return_value={
            "name": "createCard",
            "description": "Creates a card",
            "args": [],
            "type": {"name": "CardPayload", "kind": "OBJECT"},
        }
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "introspect_mutation", {"mutation_name": "createCard"}
        )
    assert result.is_error is False
    mock_introspection_client.introspect_mutation.assert_awaited_once_with(
        "createCard", max_depth=1
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "createCard" in payload["result"]


@pytest.mark.anyio
async def test_introspect_mutation_with_max_depth_passes_through(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_mutation = AsyncMock(
        return_value={
            "name": "createCard",
            "description": "Creates a card",
            "args": [],
            "type": {"name": "CardPayload", "kind": "OBJECT"},
        }
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "introspect_mutation", {"mutation_name": "createCard", "max_depth": 2}
        )
    assert result.is_error is False
    mock_introspection_client.introspect_mutation.assert_awaited_once_with(
        "createCard", max_depth=2
    )


@pytest.mark.anyio
async def test_introspect_query_with_max_depth_passes_through(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_query = AsyncMock(
        return_value={
            "name": "pipe",
            "description": "Lookup a pipe",
            "args": [],
            "type": {"name": "Pipe", "kind": "OBJECT"},
        }
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "introspect_query", {"query_name": "pipe", "max_depth": 3}
        )
    assert result.is_error is False
    mock_introspection_client.introspect_query.assert_awaited_once_with(
        "pipe", max_depth=3
    )


@pytest.mark.anyio
async def test_introspect_mutation_not_found_returns_error_payload(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_mutation = AsyncMock(
        return_value={"error": "Mutation 'missing' was not found."}
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "introspect_mutation", {"mutation_name": "missing"}
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_introspect_query_success(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_query = AsyncMock(
        return_value={
            "name": "pipe",
            "description": "Lookup a pipe by its ID",
            "args": [
                {
                    "name": "id",
                    "type": {
                        "name": None,
                        "kind": "NON_NULL",
                        "ofType": {"name": "ID", "kind": "SCALAR"},
                    },
                    "defaultValue": None,
                }
            ],
            "type": {"name": "Pipe", "kind": "OBJECT"},
        }
    )
    async with introspection_session as session:
        result = await session.call_tool("introspect_query", {"query_name": "pipe"})
    assert result.is_error is False
    mock_introspection_client.introspect_query.assert_awaited_once_with(
        "pipe", max_depth=1
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "pipe" in payload["result"]


@pytest.mark.anyio
async def test_introspect_query_not_found_returns_error_payload(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.introspect_query = AsyncMock(
        return_value={"error": "Query 'missing' was not found."}
    )
    async with introspection_session as session:
        result = await session.call_tool("introspect_query", {"query_name": "missing"})
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not found" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_search_schema_returns_matching_types(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.search_schema = AsyncMock(
        return_value={
            "types": [
                {
                    "name": "Pipe",
                    "kind": "OBJECT",
                    "description": "A pipe",
                }
            ]
        }
    )
    async with introspection_session as session:
        result = await session.call_tool("search_schema", {"keyword": "pipe"})
    assert result.is_error is False
    mock_introspection_client.search_schema.assert_awaited_once_with("pipe", kind=None)
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "Pipe" in payload["result"]


@pytest.mark.anyio
async def test_search_schema_empty_returns_success_with_empty_types(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.search_schema = AsyncMock(return_value={"types": []})
    async with introspection_session as session:
        result = await session.call_tool("search_schema", {"keyword": "zzznothing"})
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "[]" in payload["result"] or '"types": []' in payload["result"]


@pytest.mark.anyio
async def test_search_schema_with_kind_passes_through(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.search_schema = AsyncMock(
        return_value={
            "types": [
                {"name": "CardStatus", "kind": "ENUM", "description": "Status values"}
            ]
        }
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "search_schema", {"keyword": "card", "kind": "ENUM"}
        )
    assert result.is_error is False
    mock_introspection_client.search_schema.assert_awaited_once_with(
        "card", kind="ENUM"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert "CardStatus" in payload["result"]


@pytest.mark.anyio
async def test_execute_graphql_success(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.execute_graphql = AsyncMock(
        return_value={"__typename": "Query"}
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query Q { __typename }", "variables": None},
        )
    assert result.is_error is False
    mock_introspection_client.execute_graphql.assert_awaited_once_with(
        "query Q { __typename }", None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload.get("requires_confirmation") is not True
    assert "Query" in payload["result"]


@pytest.mark.anyio
async def test_execute_graphql_mutation_without_token_returns_preview(
    introspection_session, mock_introspection_client, extract_payload
):
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "mutation { __typename }"},
        )
    assert result.is_error is False
    mock_introspection_client.execute_graphql.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    token = payload["confirmation_token"]
    assert token
    assert token.startswith("v1.")
    assert payload["message"].startswith(
        "⚠️ This GraphQL mutation's effects are permanent and cannot be undone."
    )


@pytest.mark.anyio
async def test_execute_graphql_mutation_identity_hashes_are_hex(
    introspection_session, mock_introspection_client, monkeypatch
):
    captured = {}

    async def capture_guard(_ctx, **kwargs):
        captured["resource_identity"] = kwargs["resource_identity"]
        return {
            "success": False,
            "requires_confirmation": True,
            "confirmation_token": "v1.preview",
        }

    monkeypatch.setattr(
        "pipefy_mcp.tools.introspection_tools.check_destructive_confirmation",
        capture_guard,
    )
    async with introspection_session as session:
        await session.call_tool(
            "execute_graphql",
            {"query": "mutation { __typename }", "variables": {"n": 1}},
        )
    mock_introspection_client.execute_graphql.assert_not_awaited()
    identity = captured["resource_identity"]
    for value in (identity["document"], identity["variables"]):
        assert isinstance(value, str)
        assert len(value) == 64
        assert all(c in "0123456789abcdef" for c in value)


@pytest.mark.anyio
async def test_execute_graphql_mutation_with_matching_token_executes(
    introspection_session, mock_introspection_client
):
    mock_introspection_client.execute_graphql = AsyncMock(
        return_value={"__typename": "Mutation"}
    )
    async with introspection_session as session:
        payload = await confirm_after_preview(
            session,
            "execute_graphql",
            {"query": "mutation { __typename }", "confirm": True},
        )
    mock_introspection_client.execute_graphql.assert_awaited_once_with(
        "mutation { __typename }", None
    )
    assert payload["success"] is True
    assert "Mutation" in payload["result"]


@pytest.mark.anyio
async def test_execute_graphql_token_from_mutation_a_does_not_execute_mutation_b(
    introspection_session, mock_introspection_client, extract_payload
):
    async with introspection_session as session:
        preview = await session.call_tool(
            "execute_graphql",
            {"query": "mutation A { __typename }"},
        )
        token = extract_payload(preview)["confirmation_token"]
        mismatch = await session.call_tool(
            "execute_graphql",
            {
                "query": "mutation B { __typename }",
                "confirm": True,
                "confirmation_token": token,
            },
        )
    mock_introspection_client.execute_graphql.assert_not_awaited()
    payload = extract_payload(mismatch)
    assert payload["requires_confirmation"] is True


@pytest.mark.anyio
async def test_execute_graphql_token_from_variables_a_does_not_execute_variables_b(
    introspection_session, mock_introspection_client, extract_payload
):
    mutation = "mutation M($i: ID!) { __typename }"
    async with introspection_session as session:
        preview = await session.call_tool(
            "execute_graphql",
            {"query": mutation, "variables": {"i": "1"}},
        )
        token = extract_payload(preview)["confirmation_token"]
        mismatch = await session.call_tool(
            "execute_graphql",
            {
                "query": mutation,
                "variables": {"i": "2"},
                "confirm": True,
                "confirmation_token": token,
            },
        )
    mock_introspection_client.execute_graphql.assert_not_awaited()
    payload = extract_payload(mismatch)
    assert payload["requires_confirmation"] is True
    assert payload["confirmation_token"] != token


@pytest.mark.anyio
async def test_execute_graphql_mutation_previews_name_the_operation(
    introspection_session, mock_introspection_client, extract_payload
):
    async with introspection_session as session:
        preview_a = await session.call_tool(
            "execute_graphql",
            {"query": "mutation DeletePipe { deletePipe(id: 999) { id } }"},
        )
        preview_b = await session.call_tool(
            "execute_graphql",
            {"query": "mutation DeleteCard { deleteCard(id: 111) { id } }"},
        )
    mock_introspection_client.execute_graphql.assert_not_awaited()
    payload_a = extract_payload(preview_a)
    payload_b = extract_payload(preview_b)
    assert payload_a["resource"] != payload_b["resource"]
    assert "DeletePipe" in payload_a["resource"]
    assert "DeleteCard" in payload_b["resource"]


@pytest.mark.anyio
async def test_execute_graphql_preview_does_not_leak_signing_key(
    introspection_session, mock_introspection_client, extract_payload, monkeypatch
):
    canary = b"leak-canary-signing-key-bytes!!"
    monkeypatch.setattr(
        "pipefy_mcp.tools.destructive_tool_guard.signing_key_for",
        lambda _ctx: canary,
    )
    async with introspection_session as session:
        preview = await session.call_tool(
            "execute_graphql",
            {"query": "mutation { __typename }"},
        )
        invalid = await session.call_tool(
            "execute_graphql",
            {
                "query": "mutation { __typename }",
                "confirm": True,
                "confirmation_token": "not-a-token",
            },
        )
    mock_introspection_client.execute_graphql.assert_not_awaited()
    for result in (preview, invalid):
        blob = json.dumps(extract_payload(result), default=str)
        assert canary.decode() not in blob
        assert canary.hex() not in blob
        assert str(canary) not in blob


_TOO_NESTED_QUERY = "{a" * 400 + "}" * 400
_TOO_NESTED_MUTATION = "mutation { " + "a { " * 400 + "x " + "} " * 401


@pytest.mark.anyio
@pytest.mark.parametrize("query", [_TOO_NESTED_QUERY, _TOO_NESTED_MUTATION])
async def test_execute_graphql_too_nested_document_is_error_envelope(
    introspection_session, mock_introspection_client, extract_payload, query
):
    async with introspection_session as session:
        result = await session.call_tool("execute_graphql", {"query": query})
    mock_introspection_client.execute_graphql.assert_not_awaited()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload.get("requires_confirmation") is not True
    assert "nested" in tool_error_message(payload).lower()


@pytest.mark.anyio
async def test_execute_graphql_does_not_set_destructive_hint(introspection_session):
    async with introspection_session as session:
        listed = await session.list_tools()
    tool = next(t for t in listed.tools if t.name == "execute_graphql")
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is not True


@pytest.mark.anyio
async def test_execute_graphql_graphql_errors_surface_as_failure(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.execute_graphql = AsyncMock(
        return_value={
            "errors": [{"message": "Field `nope` does not exist", "extensions": {}}]
        }
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query Q { __typename }", "variables": {}},
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert (
        "nope" in tool_error_message(payload).lower()
        or "nope" in payload.get("result", "").lower()
    )


@pytest.mark.anyio
async def test_execute_graphql_syntax_error_returns_error_payload(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.execute_graphql = AsyncMock(
        return_value={"error": "Syntax Error: Expected Name, found <EOF>."}
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query { z"},
        )
    assert result.is_error is False
    mock_introspection_client.execute_graphql.assert_awaited_once()
    payload = extract_payload(result)
    assert payload["success"] is False
    err = tool_error_message(payload).lower()
    assert "syntax" in err or "invalid" in err or "unexpected" in err


@pytest.mark.anyio
async def test_execute_graphql_transport_error_returns_error_payload(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.execute_graphql = AsyncMock(
        side_effect=RuntimeError("Connection refused")
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query Q { __typename }"},
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Connection refused" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("exc_message", ["", "   "])
async def test_execute_graphql_empty_exception_message_uses_fallback(
    introspection_session, mock_introspection_client, extract_payload, exc_message
):
    mock_introspection_client.execute_graphql = AsyncMock(
        side_effect=RuntimeError(exc_message)
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query Q { __typename }"},
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload)
    assert message.strip()
    assert "GraphQL request failed." in message
    assert "re-read counts/ids" in message
    assert "do not blind-retry" in message


@pytest.mark.anyio
async def test_execute_graphql_preserves_non_empty_exception_message(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.execute_graphql = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query Q { __typename }"},
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "boom" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "client_attr", "arguments"),
    [
        ("introspect_type", "introspect_type", {"type_name": "Card"}),
        ("introspect_mutation", "introspect_mutation", {"mutation_name": "createCard"}),
        ("introspect_query", "introspect_query", {"query_name": "card"}),
        ("search_schema", "search_schema", {"keyword": "card"}),
    ],
)
@pytest.mark.parametrize("exc_message", ["", "   "])
async def test_introspection_tools_empty_exception_message_uses_fallback(
    introspection_session,
    mock_introspection_client,
    extract_payload,
    tool_name,
    client_attr,
    arguments,
    exc_message,
):
    setattr(
        mock_introspection_client,
        client_attr,
        AsyncMock(side_effect=RuntimeError(exc_message)),
    )
    async with introspection_session as session:
        result = await session.call_tool(tool_name, arguments)
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload)
    assert message.strip()
    assert "GraphQL request failed." in message


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "client_attr", "arguments"),
    [
        ("introspect_type", "introspect_type", {"type_name": "Card"}),
        ("introspect_mutation", "introspect_mutation", {"mutation_name": "createCard"}),
        ("introspect_query", "introspect_query", {"query_name": "card"}),
        ("search_schema", "search_schema", {"keyword": "card"}),
    ],
)
async def test_introspection_tools_preserves_non_empty_exception_message(
    introspection_session,
    mock_introspection_client,
    extract_payload,
    tool_name,
    client_attr,
    arguments,
):
    setattr(
        mock_introspection_client,
        client_attr,
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    async with introspection_session as session:
        result = await session.call_tool(tool_name, arguments)
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "boom" in tool_error_message(payload)


@pytest.mark.anyio
@pytest.mark.parametrize("soft_error", ["", "   "])
async def test_execute_graphql_soft_error_field_empty_or_whitespace_uses_fallback(
    introspection_session, mock_introspection_client, extract_payload, soft_error
):
    mock_introspection_client.execute_graphql = AsyncMock(
        return_value={"error": soft_error}
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query Q { __typename }"},
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    message = tool_error_message(payload)
    assert message.strip()
    assert "GraphQL returned errors." in message


@pytest.mark.anyio
async def test_execute_graphql_soft_errors_whitespace_messages_use_fallback(
    introspection_session, mock_introspection_client, extract_payload
):
    mock_introspection_client.execute_graphql = AsyncMock(
        return_value={"errors": [{"message": "   "}]}
    )
    async with introspection_session as session:
        result = await session.call_tool(
            "execute_graphql",
            {"query": "query Q { __typename }"},
        )
    assert result.is_error is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert tool_error_message(payload) == "GraphQL returned errors."
