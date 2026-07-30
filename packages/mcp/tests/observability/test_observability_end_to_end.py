"""In-process end-to-end test for the hosted observability wiring.

Drives a real ``wire_hosted_observability`` app (real session manager, real
stateful Streamable HTTP dispatch, real ``request_ctx`` propagation) through
``httpx.ASGITransport``: initialize, initialized notification, then two
sequential ``tools/call`` POSTs in the same session. This is the CI lock for
the D4 correlation design: the session task is spawned once at initialize, so
a contextvar-based correlation would stamp the initialize request id on every
tool line, and this test would fail.

Tool lines come from ``tool_log_middleware`` (#378) via the shared structured
emitter, not a second CallToolRequest wrap.

``json_response=True`` keeps responses as plain JSON (no SSE framing to
parse); the dispatch path under test, transport metadata plus per-message
``request_ctx``, is identical to the SSE-response mode.
"""

from __future__ import annotations

import json
from typing import Any

import anyio
import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from pipefy_mcp.core.tool_middleware import build_tool_call_middleware
from pipefy_mcp.observability.json_logging import (
    configure_observability_logging,
    reset_observability_logging,
)
from pipefy_mcp.observability.tool_log_middleware import tool_log_middleware
from pipefy_mcp.observability.wiring import wire_hosted_observability

_ACCEPT = "application/json, text/event-stream"


@pytest.fixture(autouse=True)
def _isolated_observability_logger():
    reset_observability_logging()
    yield
    reset_observability_logging()


def _read_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in capsys.readouterr().err.splitlines()
        if line.strip()
    ]


def _initialize_body() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "obs-e2e", "version": "0"},
        },
    }


def _call_tool_body(request_id: int, text: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": text}},
    }


@pytest.mark.anyio
async def test_two_calls_in_one_session_correlate_to_their_own_posts(capsys):
    configure_observability_logging()

    # json_response moved off the server settings onto streamable_http_app() in 2.0,
    # so it is passed through the wiring helper; middleware is a constructor argument.
    app = MCPServer(
        "obs-e2e",
        middleware=[build_tool_call_middleware([tool_log_middleware])],
    )

    @app.tool()
    def echo(text: str) -> str:
        return text

    http_app = wire_hosted_observability(app, json_response=True)

    with anyio.fail_after(15):
        async with http_app.router.lifespan_context(http_app):
            transport = httpx.ASGITransport(app=http_app)
            # Loopback base_url: the SDK's DNS-rebinding protection (default
            # TransportSecuritySettings) rejects non-local Host headers with 421.
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                init_response = await client.post(
                    "/mcp",
                    json=_initialize_body(),
                    headers={"accept": _ACCEPT},
                )
                assert init_response.status_code == 200
                session_id = init_response.headers["mcp-session-id"]
                protocol_version = init_response.json()["result"]["protocolVersion"]
                session_headers = {
                    "accept": _ACCEPT,
                    "mcp-session-id": session_id,
                    "mcp-protocol-version": protocol_version,
                }

                notified = await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers=session_headers,
                )
                assert notified.status_code == 202

                first = await client.post(
                    "/mcp",
                    json=_call_tool_body(2, "first-call"),
                    headers=session_headers,
                )
                assert first.status_code == 200
                assert first.json()["result"]["isError"] is False

                second = await client.post(
                    "/mcp",
                    json=_call_tool_body(3, "second-call"),
                    headers=session_headers,
                )
                assert second.status_code == 200

    lines = _read_log_lines(capsys)
    http_lines = [line for line in lines if line["event"] == "http_request"]
    tool_lines = [line for line in lines if line["event"] == "tool_call"]

    assert len(http_lines) == 4  # initialize, notification, two tool calls
    assert len(tool_lines) == 2

    http_request_ids = [line["request_id"] for line in http_lines]
    initialize_request_id = http_request_ids[0]

    for tool_line in tool_lines:
        assert tool_line["tool"] == "echo"
        assert tool_line["outcome"] == "ok"
        assert tool_line["arg_keys"] == ["text"]
        # Correlation: the tool line carries the id of the POST that carried
        # it, which the middleware also logged as an http_request line.
        assert tool_line["request_id"] in http_request_ids
        assert tool_line["request_id"] != initialize_request_id

    # The two calls belong to different POSTs, so their ids must differ; a
    # contextvar frozen at session start would have made them equal.
    assert tool_lines[0]["request_id"] != tool_lines[1]["request_id"]

    # Argument values never reach the structured stream.
    serialized = json.dumps(lines)
    assert "first-call" not in serialized
    assert "second-call" not in serialized

    # Every line in the same session carries the session id.
    assert {line["session_id"] for line in http_lines} == {session_id}
