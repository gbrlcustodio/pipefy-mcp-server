"""Unit tests for the structured tool-call logging middleware.

Pins the log shape and the two protocol-safety invariants: the outcome derives
from the call result, and output goes through the hosted structured emitter on
stderr, never stdout, so it cannot corrupt the stdio JSON-RPC stream.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp import UrlElicitationRequiredError, types

from pipefy_mcp.auth.request_identity import CallerIdentity
from pipefy_mcp.core.tool_middleware import ToolCallContext
from pipefy_mcp.observability.json_logging import (
    TOOL_CALL_EVENT_KEYS,
    configure_observability_logging,
    reset_observability_logging,
)
from pipefy_mcp.observability.tool_log_middleware import tool_log_middleware


def _context(**arguments: object) -> ToolCallContext:
    return ToolCallContext(
        argument_keys=tuple(sorted(arguments)),
        identity=CallerIdentity(client_id="acting-client", scopes=("read",)),
        protocol_version="2025-11-25",
        request_id="req-42",
        tool_name="get_card",
        arguments=dict(arguments) or None,
    )


def _ok_result() -> dict:
    """A successful tool call as the middleware really sees it: the wire dict.

    ``ServerRunner._inner`` serializes the handler result before returning it into the
    middleware chain, so a middleware never sees a ``CallToolResult`` model from a real
    call - success or failure. A model fixture here is the same mismatch that let the
    outcome-logging regression through on the error path: it type-checks, it reads
    fine, and it exercises a branch production never takes.
    """
    return {"content": [{"type": "text", "text": "ok"}], "isError": False}


def _read_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict]:
    return [
        json.loads(line)
        for line in capsys.readouterr().err.splitlines()
        if line.strip()
    ]


@pytest.fixture(autouse=True)
def _isolated_observability_logger():
    reset_observability_logging()
    yield
    reset_observability_logging()


def _configure_for_capture() -> None:
    # Must run inside the test body so StreamHandler binds the capsys-redirected
    # stderr, not the process's original stream.
    configure_observability_logging()


@pytest.mark.unit
def test_logs_one_line_with_the_documented_fields(capsys):
    _configure_for_capture()

    async def terminal(ctx):
        return _ok_result()

    asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    lines = _read_log_lines(capsys)
    assert len(lines) == 1
    event = lines[0]
    assert set(event.keys()) == TOOL_CALL_EVENT_KEYS
    assert event["event"] == "tool_call"
    assert event["tool"] == "get_card"
    assert event["outcome"] == "ok"
    assert event["arg_keys"] == ["card_id"]
    assert event["client_id"] == "acting-client"
    assert event["request_id"] == "req-42"
    assert isinstance(event["duration_ms"], (int, float))
    assert "timestamp" in event


@pytest.mark.unit
def test_never_logs_argument_values_or_a_bearer(capsys):
    _configure_for_capture()

    async def terminal(ctx):
        return _ok_result()

    asyncio.run(tool_log_middleware(_context(token="super-secret-bearer"), terminal))

    raw = capsys.readouterr().err
    assert "super-secret-bearer" not in raw
    assert "token" in json.loads(raw.strip())["arg_keys"]


@pytest.mark.unit
def test_error_result_logs_outcome_error_for_the_wire_dict(capsys):
    """A failing tool call reports ``error``, read off the shape the SDK really returns.

    This is the shape that matters: the SDK's handler serializes the result for the
    wire INSIDE the middleware chain, so a real tool failure arrives as a dict keyed
    ``isError`` in camelCase, not as a model. A test that hands the middleware a
    ``CallToolResult`` instead passes while every production failure logs ``ok``,
    which is exactly the regression this test exists to catch.
    """
    _configure_for_capture()

    async def terminal(ctx):
        return {
            "content": [
                {"type": "text", "text": "Error executing tool get_card: boom"}
            ],
            "isError": True,
        }

    asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    assert _read_log_lines(capsys)[0]["outcome"] == "error"


@pytest.mark.unit
def test_error_result_logs_outcome_error_for_a_model_shape(capsys):
    """An inner middleware's own ``CallToolResult`` reports ``error`` too.

    Both shapes reach the chain, so both have to read correctly. The wire dict covers
    every result that came through the SDK's handler (and every ``short_circuit_error``,
    which shapes itself for the negotiated revision); a model only ever arrives from an
    inner middleware that built its result by hand and returned it without awaiting
    ``call_next``. That is still supported, and its flag is snake_case ``is_error``.
    """
    _configure_for_capture()

    async def terminal(ctx):
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="quota exceeded")],
            is_error=True,
        )

    asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    assert _read_log_lines(capsys)[0]["outcome"] == "error"


@pytest.mark.unit
def test_cancellation_logs_outcome_cancelled_and_re_raises(capsys):
    """A client disconnect is control flow, not an error, and must propagate."""
    _configure_for_capture()

    async def terminal(ctx):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    assert _read_log_lines(capsys)[0]["outcome"] == "cancelled"


@pytest.mark.unit
def test_elicitation_logs_outcome_elicitation_and_re_raises(capsys):
    """A URL-elicitation signal is a continuation, not an error, and must propagate."""
    _configure_for_capture()

    async def terminal(ctx):
        raise UrlElicitationRequiredError([])

    with pytest.raises(UrlElicitationRequiredError):
        asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    assert _read_log_lines(capsys)[0]["outcome"] == "elicitation"


@pytest.mark.unit
def test_other_propagated_exception_logs_outcome_error_and_re_raises(capsys):
    """Any other propagating exception is logged as an error and re-raised."""
    _configure_for_capture()

    class Boom(Exception):
        pass

    async def terminal(ctx):
        raise Boom("propagate me")

    with pytest.raises(Boom, match="propagate me"):
        asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    assert _read_log_lines(capsys)[0]["outcome"] == "error"


@pytest.mark.unit
def test_writes_nothing_to_stdout(capsys):
    """The emitter must never touch stdout: it is the stdio transport's JSON-RPC stream."""
    _configure_for_capture()

    async def terminal(ctx):
        return _ok_result()

    asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    captured = capsys.readouterr()
    assert captured.out == ""
    assert '"event":"tool_call"' in captured.err
