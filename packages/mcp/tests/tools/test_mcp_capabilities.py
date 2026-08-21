"""Tests for MCP client capability introspection helpers."""

import json
from types import SimpleNamespace
from typing import Any

import anyio
import httpx
import pytest
from mcp.server.mcpserver import Context, MCPServer

from pipefy_mcp.observability.wiring import wire_hosted_observability
from pipefy_mcp.tools.mcp_capabilities import supports_elicitation


def test_no_session_returns_false():
    ctx = SimpleNamespace()
    assert supports_elicitation(ctx) is False


def test_no_client_params_returns_false():
    ctx = SimpleNamespace(session=SimpleNamespace())
    assert supports_elicitation(ctx) is False


def test_no_capabilities_returns_false():
    session = SimpleNamespace(client_params=SimpleNamespace())
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is False


def test_elicitation_false_returns_false():
    caps = SimpleNamespace(elicitation=False)
    session = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=caps),
    )
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is False


def test_elicitation_true_returns_true():
    caps = SimpleNamespace(elicitation=True)
    session = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=caps),
    )
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is True


def test_capabilities_without_elicitation_attr_returns_false():
    session = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=SimpleNamespace()),
    )
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is False


def test_advertised_elicitation_without_a_back_channel_returns_false():
    """Protocol revision 2026-07-28 advertises elicitation but cannot be called.

    A client on that revision still declares the ``elicitation`` capability in
    its request envelope, while ``can_send_request`` is ``False`` because the
    revision has no server-to-client channel. Gating on the capability alone
    lets ``ctx.elicit`` through, and it raises ``NoBackChannelError``.
    """
    caps = SimpleNamespace(elicitation=True)
    session = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=caps),
        can_send_request=False,
    )
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is False


def test_advertised_elicitation_with_a_back_channel_returns_true():
    caps = SimpleNamespace(elicitation=True)
    session = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=caps),
        can_send_request=True,
    )
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is True


def test_session_without_can_send_request_attr_is_treated_as_sendable():
    """An unmeasurable channel is attempted, not pre-emptively refused.

    Older SDKs and hand-built doubles expose no ``can_send_request``. Treating
    that as unsendable would silently disable elicitation everywhere it is
    absent; the ``NoBackChannelError`` handling at the elicitation call site is
    what covers the case where the channel really is missing.
    """
    caps = SimpleNamespace(elicitation=True)
    session = SimpleNamespace(client_params=SimpleNamespace(capabilities=caps))
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is True


_ACCEPT = "application/json, text/event-stream"


def _payloads(response: httpx.Response) -> list[dict[str, Any]]:
    if response.headers["content-type"].startswith("text/event-stream"):
        return [
            json.loads(line.removeprefix("data:").strip())
            for line in response.text.splitlines()
            if line.startswith("data:")
        ]
    return [response.json()]


async def _gate_over_the_wire(*, json_response: bool) -> dict[str, Any]:
    """Drive a tool through the real ASGI stack and report what the gate saw.

    A stateful Streamable HTTP session (the handshake returns an
    ``mcp-session-id``) on a revision that has a back channel, with the client
    advertising ``elicitation``. The only variable is ``json_response``.
    """
    app = MCPServer("gate-probe")

    @app.tool()
    async def probe(ctx: Context) -> dict:
        return {
            "supports_elicitation": supports_elicitation(ctx),
            "can_send_request": ctx.session.can_send_request,
        }

    http_app = wire_hosted_observability(app, json_response=json_response)
    async with http_app.router.lifespan_context(http_app):
        transport = httpx.ASGITransport(app=http_app)
        # Loopback base_url: the SDK's default DNS-rebinding protection answers
        # 421 for a non-local Host header.
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8000"
        ) as client:
            init = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"elicitation": {}},
                        "clientInfo": {"name": "gate-probe", "version": "0"},
                    },
                },
                headers={"accept": _ACCEPT},
            )
            assert init.status_code == 200
            negotiated = _payloads(init)[0]["result"]["protocolVersion"]
            session_id = init.headers["mcp-session-id"]
            headers = {
                "accept": _ACCEPT,
                "mcp-protocol-version": negotiated,
                "mcp-session-id": session_id,
            }
            await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers=headers,
            )
            call = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "probe", "arguments": {}},
                },
                headers=headers,
            )
            result = _payloads(call)[-1]["result"]
            measured = json.loads(result["content"][0]["text"])
            return {"negotiated": negotiated, **measured}


@pytest.mark.anyio
async def test_json_response_mode_has_no_back_channel_at_a_modern_handshake():
    """``json_response=True`` costs elicitation, and the docstring says so.

    A JSON body carries only the response, so
    ``StreamableHTTPServerTransport._message_metadata`` stamps
    ``can_send_request=not is_json_response_enabled``. This holds at 2025-11-25,
    a revision that does have a back channel, and on a stateful session, so
    neither of the other two no-channel cases explains it.

    Pinned because ``json_response=True`` is what the hosted wrapper serves
    (``pipefy_remote_mcp.asgi``): elicitation is unavailable there at every
    revision, which is a product-visible fact and not only a doc detail.
    """
    with anyio.fail_after(20):
        measured = await _gate_over_the_wire(json_response=True)
    assert measured["negotiated"] == "2025-11-25"
    assert measured["can_send_request"] is False
    assert measured["supports_elicitation"] is False


@pytest.mark.anyio
async def test_sse_framed_mode_keeps_the_back_channel_at_the_same_revision():
    """The control for the case above: only ``json_response`` changed."""
    with anyio.fail_after(20):
        measured = await _gate_over_the_wire(json_response=False)
    assert measured["negotiated"] == "2025-11-25"
    assert measured["can_send_request"] is True
    assert measured["supports_elicitation"] is True
