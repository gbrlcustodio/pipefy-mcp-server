"""Unit tests for the structured tool-call logging middleware.

Pins the log shape and the two protocol-safety invariants: the outcome derives
from the call result, and output goes to logging (stderr), never stdout, so it
cannot corrupt the stdio JSON-RPC stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import pytest
from mcp import UrlElicitationRequiredError, types

from pipefy_mcp.auth.request_identity import CallerIdentity
from pipefy_mcp.core.tool_middleware import ToolCallContext
from pipefy_mcp.observability.tool_log_middleware import tool_log_middleware


def _context(**arguments: object) -> ToolCallContext:
    req = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name="get_card", arguments=arguments),
    )
    return ToolCallContext(
        argument_keys=tuple(sorted(arguments)),
        identity=CallerIdentity(client_id="acting-client", scopes=("read",)),
        request_id="req-42",
        req=req,
    )


def _ok_result() -> types.ServerResult:
    return types.ServerResult(
        types.CallToolResult(content=[types.TextContent(type="text", text="ok")])
    )


def _log_line(caplog) -> dict:
    records = [
        r for r in caplog.records if r.name == "pipefy_mcp.observability.tool_call"
    ]
    assert len(records) == 1
    return json.loads(records[0].getMessage())


@pytest.mark.unit
def test_logs_one_line_with_the_documented_fields(caplog):
    async def terminal(ctx):
        return _ok_result()

    with caplog.at_level(logging.INFO, logger="pipefy_mcp.observability.tool_call"):
        asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    event = _log_line(caplog)
    assert event["tool"] == "get_card"
    assert event["outcome"] == "ok"
    assert event["arg_keys"] == ["card_id"]
    assert event["client_id"] == "acting-client"
    assert event["request_id"] == "req-42"
    assert isinstance(event["duration_ms"], (int, float))


@pytest.mark.unit
def test_never_logs_argument_values_or_a_bearer(caplog):
    async def terminal(ctx):
        return _ok_result()

    with caplog.at_level(logging.INFO, logger="pipefy_mcp.observability.tool_call"):
        asyncio.run(
            tool_log_middleware(_context(token="super-secret-bearer"), terminal)
        )

    raw = caplog.records[-1].getMessage()
    assert "super-secret-bearer" not in raw
    assert "token" in json.loads(raw)["arg_keys"]  # the key is logged, not the value


@pytest.mark.unit
def test_error_result_logs_outcome_error(caplog):
    async def terminal(ctx):
        return types.ServerResult(
            types.CallToolResult(
                content=[types.TextContent(type="text", text="boom")], isError=True
            )
        )

    with caplog.at_level(logging.INFO, logger="pipefy_mcp.observability.tool_call"):
        asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    assert _log_line(caplog)["outcome"] == "error"


@pytest.mark.unit
def test_cancellation_logs_outcome_cancelled_and_re_raises(caplog):
    """A client disconnect is control flow, not an error, and must propagate."""

    async def terminal(ctx):
        raise asyncio.CancelledError

    with caplog.at_level(logging.INFO, logger="pipefy_mcp.observability.tool_call"):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    assert _log_line(caplog)["outcome"] == "cancelled"


@pytest.mark.unit
def test_elicitation_logs_outcome_elicitation_and_re_raises(caplog):
    """A URL-elicitation signal is a continuation, not an error, and must propagate."""

    async def terminal(ctx):
        raise UrlElicitationRequiredError([])

    with caplog.at_level(logging.INFO, logger="pipefy_mcp.observability.tool_call"):
        with pytest.raises(UrlElicitationRequiredError):
            asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    assert _log_line(caplog)["outcome"] == "elicitation"


@pytest.mark.unit
def test_other_propagated_exception_logs_outcome_error_and_re_raises(caplog):
    """Any other propagating exception is logged as an error and re-raised."""

    class Boom(Exception):
        pass

    async def terminal(ctx):
        raise Boom("propagate me")

    with caplog.at_level(logging.INFO, logger="pipefy_mcp.observability.tool_call"):
        with pytest.raises(Boom, match="propagate me"):
            asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))

    assert _log_line(caplog)["outcome"] == "error"


@pytest.mark.unit
def test_writes_nothing_to_stdout(capsys):
    """The logger must never touch stdout: it is the stdio transport's JSON-RPC stream."""

    async def terminal(ctx):
        return _ok_result()

    # Route logging to stderr explicitly, then assert stdout stays empty.
    handler = logging.StreamHandler(sys.stderr)
    log = logging.getLogger("pipefy_mcp.observability.tool_call")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        asyncio.run(tool_log_middleware(_context(card_id="1"), terminal))
    finally:
        log.removeHandler(handler)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert '"event":"tool_call"' in captured.err
