"""Tests for hosted observability wiring through the real auth stack.

Unit tests inject ``scope["user"]`` directly and only prove extraction. These
tests drive ``wire_hosted_observability`` so AuthenticationMiddleware populates
``scope["user"]`` before RequestLogMiddleware's ``finally`` reads it — locking
middleware order and identity fields together.
"""

from __future__ import annotations

import json
from typing import Any

import anyio
import httpx
import pytest
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings as FastMcpAuthSettings
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

from pipefy_mcp.auth.resource_server import PipefyAccessToken
from pipefy_mcp.observability.json_logging import (
    configure_observability_logging,
    reset_observability_logging,
)
from pipefy_mcp.observability.wiring import wire_hosted_observability

_ACCEPT = "application/json, text/event-stream"
_GOOD_TOKEN = "good-token"
_CLIENT_ID = "client-abc"
_SUB = "user-123"


class _StubTokenVerifier:
    """Accept one fixed bearer and map it to a PipefyAccessToken with sub."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if token != _GOOD_TOKEN:
            return None
        return PipefyAccessToken(
            token=token,
            client_id=_CLIENT_ID,
            scopes=["read"],
            expires_at=None,
            resource="https://mcp.example.com/mcp",
            sub=_SUB,
        )


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


def _build_auth_http_app() -> Starlette:
    app = FastMCP(
        "wiring-identity",
        token_verifier=_StubTokenVerifier(),
        auth=FastMcpAuthSettings(
            issuer_url="https://issuer.example.com",
            resource_server_url="https://mcp.example.com/mcp",
        ),
    )
    app.settings.json_response = True
    return wire_hosted_observability(app)


@pytest.mark.anyio
async def test_wired_app_logs_null_identity_without_bearer(capsys):
    """UnauthenticatedUser from the real auth stack yields null sub/client_id."""
    configure_observability_logging()
    http_app = _build_auth_http_app()

    with anyio.fail_after(10):
        async with http_app.router.lifespan_context(http_app):
            transport = httpx.ASGITransport(app=http_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                response = await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                    headers={"accept": _ACCEPT},
                )

    assert response.status_code == 401
    lines = [
        line for line in _read_log_lines(capsys) if line.get("event") == "http_request"
    ]
    assert len(lines) == 1
    assert lines[0]["sub"] is None
    assert lines[0]["client_id"] is None
    assert lines[0]["status"] == 401


@pytest.mark.anyio
async def test_wired_app_logs_sub_and_client_id_from_auth_stack(capsys):
    """AuthenticatedUser set by BearerAuthBackend reaches RequestLogMiddleware."""
    configure_observability_logging()
    http_app = _build_auth_http_app()

    with anyio.fail_after(10):
        async with http_app.router.lifespan_context(http_app):
            transport = httpx.ASGITransport(app=http_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                response = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "wiring-identity", "version": "0"},
                        },
                    },
                    headers={
                        "accept": _ACCEPT,
                        "authorization": f"Bearer {_GOOD_TOKEN}",
                    },
                )

    assert response.status_code == 200
    lines = [
        line for line in _read_log_lines(capsys) if line.get("event") == "http_request"
    ]
    assert len(lines) == 1
    assert lines[0]["sub"] == _SUB
    assert lines[0]["client_id"] == _CLIENT_ID
    assert _GOOD_TOKEN not in json.dumps(lines)
