import json

import pytest

from pipefy_mcp.tools import pipe_tools


class _FakeGraphQLException(Exception):
    """Test helper: mimics a gql exception exposing `.errors` with `message` fields."""

    def __init__(self, message: str, errors: list[dict] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class _FakePipefyClient:
    async def add_card_comment(self, card_id: int, text: str) -> dict:  # noqa: ARG002
        return {"createComment": {"comment": {"id": "c_987"}}}


def _extract_call_tool_payload(result) -> dict:
    """Extract tool payload from CallToolResult across MCP SDK versions.

    Some versions populate `structuredContent`, while others return JSON in `content` text.
    """
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        if isinstance(structured, dict) and "result" in structured:
            payload = structured.get("result")
            if isinstance(payload, dict):
                return payload
        if isinstance(structured, dict):
            return structured

    content = getattr(result, "content", None) or []
    for item in content:
        if getattr(item, "type", None) == "text":
            text = getattr(item, "text", "")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload

    raise AssertionError("Could not extract tool payload from CallToolResult")


@pytest.mark.unit
@pytest.mark.parametrize("card_id", [0, -1, -999])
def test_validate_add_card_comment_input_rejects_card_id_zero_or_negative(card_id: int):
    """Tool validation should reject card_id <= 0."""
    with pytest.raises(ValueError, match=r"card_id must be a positive integer"):
        pipe_tools.validate_add_card_comment_input(card_id=card_id, text="ok")  # type: ignore[attr-defined]


@pytest.mark.unit
@pytest.mark.parametrize("text", ["", "   ", "\n\t  "])
def test_validate_add_card_comment_input_rejects_blank_or_whitespace_text(text: str):
    """Tool validation should reject blank/whitespace-only text."""
    with pytest.raises(ValueError, match=r"text must not be blank"):
        pipe_tools.validate_add_card_comment_input(card_id=1, text=text)  # type: ignore[attr-defined]


@pytest.mark.unit
def test_validate_add_card_comment_input_rejects_text_over_max_length():
    """Tool validation should reject text longer than the maximum length."""
    too_long_text = "a" * (pipe_tools.MAX_COMMENT_TEXT_LENGTH + 1)  # type: ignore[attr-defined]
    with pytest.raises(
        ValueError,
        match=rf"text must be at most {pipe_tools.MAX_COMMENT_TEXT_LENGTH} characters",  # type: ignore[attr-defined]
    ):
        pipe_tools.validate_add_card_comment_input(card_id=1, text=too_long_text)  # type: ignore[attr-defined]


@pytest.mark.unit
def test_validate_add_card_comment_input_accepts_text_at_max_length_boundary():
    """Tool validation should accept text exactly at the max length boundary."""
    text = "a" * pipe_tools.MAX_COMMENT_TEXT_LENGTH  # type: ignore[attr-defined]
    pipe_tools.validate_add_card_comment_input(card_id=1, text=text)  # type: ignore[attr-defined]


@pytest.mark.unit
def test_build_add_card_comment_success_payload_contract_with_string_id():
    """Tool success payload must follow the public contract."""
    payload = pipe_tools.build_add_card_comment_success_payload(comment_id="c_987")  # type: ignore[attr-defined]
    assert payload == {"success": True, "comment_id": "c_987"}


@pytest.mark.unit
def test_build_add_card_comment_success_payload_stringifies_id():
    """Tool success payload should always expose comment_id as a string."""
    payload = pipe_tools.build_add_card_comment_success_payload(comment_id=123)  # type: ignore[arg-type,attr-defined]
    assert payload == {"success": True, "comment_id": "123"}


@pytest.mark.unit
def test_map_add_card_comment_error_to_message_card_not_found():
    """GraphQL errors indicating missing/invalid card should map to a friendly message."""
    exc = _FakeGraphQLException(
        message="Record not found",
        errors=[{"message": "Card not found"}],
    )

    msg = pipe_tools.map_add_card_comment_error_to_message(exc)  # type: ignore[attr-defined]
    assert msg == "Card not found. Please verify 'card_id' and access permissions."


@pytest.mark.unit
def test_map_add_card_comment_error_to_message_permission_denied():
    """GraphQL errors indicating lack of permission should map to a friendly message."""
    exc = _FakeGraphQLException(
        message="You do not have permission to perform this action",
        errors=[{"message": "Not authorized"}],
    )

    msg = pipe_tools.map_add_card_comment_error_to_message(exc)  # type: ignore[attr-defined]
    assert msg == "You don't have permission to comment on this card."


@pytest.mark.unit
def test_map_add_card_comment_error_to_message_generic_fallback():
    """Unknown errors should map to a stable generic message (no raw details)."""
    exc = RuntimeError("socket hang up")

    msg = pipe_tools.map_add_card_comment_error_to_message(exc)  # type: ignore[attr-defined]
    assert msg == "Unexpected error while adding comment. Please try again."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_card_comment_tool_can_be_called_via_in_memory_mcp_session():
    """Tool should be registered and callable via MCP in-memory transport."""
    from mcp.server.fastmcp import FastMCP
    from mcp.shared.memory import create_connected_server_and_client_session

    from pipefy_mcp.tools.pipe_tools import PipeTools

    fake_client = _FakePipefyClient()
    app = FastMCP("test-pipefy-mcp")
    PipeTools.register(app, fake_client)  # type: ignore[arg-type]

    result = None
    async with create_connected_server_and_client_session(
        app, raise_exceptions=True
    ) as client_session:
        result = await client_session.call_tool(
            "add_card_comment",
            {"card_id": 123, "text": "hello"},
        )

    assert result is not None
    payload = _extract_call_tool_payload(result)
    assert payload == {"success": True, "comment_id": "c_987"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_card_comment_tool_invalid_input_returns_error_payload():
    """Tool should return a stable error payload on validation failures."""
    from mcp.server.fastmcp import FastMCP
    from mcp.shared.memory import create_connected_server_and_client_session

    from pipefy_mcp.tools.pipe_tools import PipeTools

    fake_client = _FakePipefyClient()
    app = FastMCP("test-pipefy-mcp")
    PipeTools.register(app, fake_client)  # type: ignore[arg-type]

    result = None
    async with create_connected_server_and_client_session(
        app, raise_exceptions=True
    ) as client_session:
        result = await client_session.call_tool(
            "add_card_comment",
            {"card_id": 0, "text": "hello"},
        )

    assert result is not None
    payload = _extract_call_tool_payload(result)
    assert payload == {
        "success": False,
        "error": "Invalid input. Please provide a valid 'card_id' and non-empty 'text'.",
    }
