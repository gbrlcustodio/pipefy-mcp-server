"""Tests for the PipefyValidationTool argument-error envelope."""

from datetime import timedelta

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.exceptions import UrlElicitationRequiredError
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from mcp.types import ElicitRequestURLParams
from pydantic import BaseModel, ValidationError

from pipefy_mcp.tools.validation_envelope import (
    PipefyValidationTool,
    _format_validation_errors,
    _serialize_errors,
)
from tests.tools.conftest import assert_invalid_arguments_envelope


@pytest.fixture
def mcp_server():
    mcp = FastMCP("envelope-test-server")

    @mcp.tool(description="Probe tool for envelope tests.")
    async def probe(pipe_id: int, actions: list[str], confirm: bool = False) -> dict:
        return {
            "success": True,
            "pipe_id": pipe_id,
            "actions": actions,
            "confirm": confirm,
        }

    @mcp.tool(description="Tool whose required arg is named 'uuid' on purpose.")
    async def delete_probe(uuid: str, confirm: bool = True) -> dict:
        return {"success": True, "uuid": uuid, "confirm": confirm}

    return mcp


@pytest.fixture
def client_session(mcp_server):
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


@pytest.mark.anyio
class TestEnvelopeAgainstLiveServer:
    async def test_missing_required_arg_returns_envelope(self, client_session):
        async with client_session as session:
            result = await session.call_tool("probe", {"actions": ["a"]})

        payload = assert_invalid_arguments_envelope(result)
        message = payload["error"]["message"]
        assert "missing required argument 'pipe_id'" in message
        assert "pydantic.dev" not in message
        assert "Arguments" not in message
        details = payload["error"]["details"]
        assert isinstance(details["errors"], list) and details["errors"]
        first = details["errors"][0]
        assert set(first.keys()) == {"path", "type", "message"}

    async def test_wrong_arg_name_returns_envelope(self, client_session):
        async with client_session as session:
            result = await session.call_tool(
                "delete_probe", {"ai_agent_uuid": "x", "confirm": True}
            )

        payload = assert_invalid_arguments_envelope(result)
        message = payload["error"]["message"]
        assert ("missing required argument 'uuid'" in message) or (
            "unknown argument 'ai_agent_uuid'" in message
        )
        assert "pydantic.dev" not in message

    async def test_wrong_type_returns_envelope(self, client_session):
        async with client_session as session:
            result = await session.call_tool(
                "probe", {"pipe_id": 42, "actions": "card.create"}
            )

        payload = assert_invalid_arguments_envelope(result)
        message = payload["error"]["message"]
        assert "actions" in message
        assert "pydantic.dev" not in message


class TestFormatters:
    def test_format_has_no_pydantic_noise(self):
        class _Probe(BaseModel):
            x: int
            y: list[str]

        try:
            _Probe.model_validate({})
        except ValidationError as exc:
            message = _format_validation_errors(exc, "probe")

        assert "pydantic.dev" not in message
        assert "Arguments" not in message
        assert message.startswith("Tool 'probe' received invalid arguments:")
        assert "missing required argument 'x'" in message
        assert "missing required argument 'y'" in message

    def test_serialize_errors_keeps_minimal_keys(self):
        class _Probe(BaseModel):
            x: int

        try:
            _Probe.model_validate({})
        except ValidationError as exc:
            serialized = _serialize_errors(exc)

        assert isinstance(serialized, list)
        assert serialized
        first = serialized[0]
        assert set(first.keys()) == {"path", "type", "message"}
        assert first["path"] == ["x"]
        assert first["type"] == "missing"


@pytest.mark.anyio
class TestEnvelopeBoundaryCases:
    async def test_url_elicitation_required_not_rewrapped(self):
        elicitation = ElicitRequestURLParams(
            mode="url",
            message="auth required",
            url="https://example.com/oauth/authorize",
            elicitationId="auth-test-001",
        )

        async def _fn() -> dict:
            raise UrlElicitationRequiredError([elicitation])

        tool = PipefyValidationTool.from_function(_fn, name="url_elicit_probe")

        with pytest.raises(UrlElicitationRequiredError):
            await tool.run({})

    async def test_tool_body_validation_error_unaffected(self):
        class _Inner(BaseModel):
            required_field: int

        async def _fn(payload: dict) -> dict:
            _Inner.model_validate(payload)
            return {"success": True}

        tool = PipefyValidationTool.from_function(_fn, name="inner_validator_probe")

        with pytest.raises(ToolError) as excinfo:
            await tool.run({"payload": {}})

        assert isinstance(excinfo.value.__cause__, ValidationError)
