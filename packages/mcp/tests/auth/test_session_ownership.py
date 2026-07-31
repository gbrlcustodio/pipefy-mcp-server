"""The SDK's per-session credential binding must discriminate per user, not per client.

``mcp`` 2.0 records the authorization context that created a Streamable HTTP session
and answers ``404 Session not found`` when a later request presents a different one
(``streamable_http_manager._handle_stateful_request``). That context is the
``(client_id, issuer, subject)`` triple ``mcp.server.auth.provider.principal_components``
derives from the ``AccessToken`` our :class:`JwtTokenVerifier` returns.

The hosted server is reached through one public OAuth client (``pipefy-mcp``,
see the install command in ``README.md``), so ``azp`` -- and therefore
``client_id`` -- is the same value for every end user. A verifier that supplies
only ``client_id`` collapses the triple to that one constant and the check stops
distinguishing users: any authenticated caller could present any other caller's
``mcp-session-id``. These tests drive the real manager over the real verifier so
that a mapping that stops populating ``subject`` fails here rather than in
production.
"""

from __future__ import annotations

from typing import Any

import anyio
import httpx
import pytest
from mcp.server.auth.middleware.bearer_auth import (
    AuthenticatedUser,
    authorization_context,
)
from mcp.server.auth.settings import AuthSettings as SdkAuthSettings
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette

from pipefy_mcp.auth import JwtTokenVerifier

_ACCEPT = "application/json, text/event-stream"
_RESOURCE = "https://mcp.example.com/mcp"
_ISSUER = "https://signin.example.com/realms/pipefy"
_EXP = 1893456000

# The one public OAuth client every hosted end user authorizes through, so `azp`
# is identical for user A and user B and only `sub` tells them apart.
_SHARED_CLIENT = "pipefy-mcp"
_TOKEN_A = "bearer-for-user-a"
_TOKEN_B = "bearer-for-user-b"
_SUBJECTS = {_TOKEN_A: "user-a", _TOKEN_B: "user-b"}


class _TwoUserValidator:
    """Two bearers of the same OAuth client, differing only in `sub`."""

    def validate(self, token: str) -> dict[str, Any]:
        if token not in _SUBJECTS:
            raise ValueError("unknown token")
        return {
            "azp": _SHARED_CLIENT,
            "sub": _SUBJECTS[token],
            "iss": _ISSUER,
            "exp": _EXP,
        }


def _verifier() -> JwtTokenVerifier:
    return JwtTokenVerifier(_TwoUserValidator(), resource=_RESOURCE)


def _build_http_app() -> Starlette:
    app = MCPServer(
        "session-ownership",
        token_verifier=_verifier(),
        auth=SdkAuthSettings(issuer_url=_ISSUER, resource_server_url=_RESOURCE),
    )
    # Plain JSON replies so a response body reads without an SSE parser. Session
    # ownership is decided by the manager before the transport frames anything,
    # so the framing does not affect what these tests assert.
    return app.streamable_http_app(json_response=True)


def _initialize_body() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "session-ownership", "version": "0"},
        },
    }


def _headers(token: str, session_id: str | None = None) -> dict[str, str]:
    headers = {"accept": _ACCEPT, "authorization": f"Bearer {token}"}
    if session_id is not None:
        headers["mcp-session-id"] = session_id
    return headers


# --- the discriminating property, through the real session manager -----------


@pytest.mark.anyio
async def test_a_second_user_of_the_same_oauth_client_cannot_use_the_session() -> None:
    """User B presenting user A's session id is refused as if the session were gone.

    The whole point of the check: A and B share `azp`, so `client_id` alone cannot
    tell them apart. If the verifier stopped supplying `subject`, B's request would
    be served on A's session and this assertion would fail.
    """
    http_app = _build_http_app()

    with anyio.fail_after(10):
        async with http_app.router.lifespan_context(http_app):
            transport = httpx.ASGITransport(app=http_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                created = await client.post(
                    "/mcp", json=_initialize_body(), headers=_headers(_TOKEN_A)
                )
                assert created.status_code == 200
                session_id = created.headers["mcp-session-id"]

                hijacked = await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
                    headers=_headers(_TOKEN_B, session_id),
                )

    assert hijacked.status_code == 404
    # The refusal must not disclose that the session exists.
    assert hijacked.json()["error"]["message"] == "Session not found"


@pytest.mark.anyio
async def test_the_creating_user_keeps_using_their_own_session() -> None:
    """The control: the check rejects the other user, not every follow-up request."""
    http_app = _build_http_app()

    with anyio.fail_after(10):
        async with http_app.router.lifespan_context(http_app):
            transport = httpx.ASGITransport(app=http_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8000"
            ) as client:
                created = await client.post(
                    "/mcp", json=_initialize_body(), headers=_headers(_TOKEN_A)
                )
                assert created.status_code == 200
                session_id = created.headers["mcp-session-id"]

                await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers=_headers(_TOKEN_A, session_id),
                )
                reused = await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
                    headers=_headers(_TOKEN_A, session_id),
                )

    assert reused.status_code == 200
    assert reused.json()["id"] == 2


# --- the same property at the unit level, on the triple itself ---------------


@pytest.mark.unit
async def test_two_subjects_of_one_client_are_distinct_authorization_contexts() -> None:
    """Two users of one OAuth client must not share an authorization context.

    The manager compares these dicts with ``!=``, so equality here is exactly
    "B may use A's session".
    """
    verifier = _verifier()
    token_a = await verifier.verify_token(_TOKEN_A)
    token_b = await verifier.verify_token(_TOKEN_B)
    assert token_a is not None and token_b is not None

    context_a = authorization_context(AuthenticatedUser(token_a))
    context_b = authorization_context(AuthenticatedUser(token_b))

    assert context_a["client_id"] == context_b["client_id"] == _SHARED_CLIENT
    assert context_a["subject"] == "user-a"
    assert context_b["subject"] == "user-b"
    assert context_a["issuer"] == context_b["issuer"] == _ISSUER
    assert context_a != context_b


@pytest.mark.unit
async def test_the_same_credential_yields_a_stable_authorization_context() -> None:
    """Two requests bearing one user's token must compare equal, or no session works."""
    verifier = _verifier()
    first = await verifier.verify_token(_TOKEN_A)
    second = await verifier.verify_token(_TOKEN_A)
    assert first is not None and second is not None
    assert authorization_context(AuthenticatedUser(first)) == authorization_context(
        AuthenticatedUser(second)
    )
