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

Because ``subject`` is what carries the check, the *shape* of the ``sub`` claim is
part of the security contract, not a formatting detail: any two ``sub`` values that
normalize to one ``subject`` are two principals sharing a session. So the shape
cases are driven through the real manager here too, next to the property they
protect, rather than being left to an equality assertion on the token. See
:func:`pipefy_mcp.auth.resource_server._subject` for the normalization and the one
waived case (a bearer with no ``sub`` at all).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
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
# The authority the requests present in `Host`. The client derives it from its
# base_url; the hand-built scope in `_attach_status` has to state it.
_AUTHORITY = "127.0.0.1:8000"
_RESOURCE = "https://mcp.example.com/mcp"
_ISSUER = "https://signin.example.com/realms/pipefy"
_EXP = 1893456000

# The one public OAuth client every hosted end user authorizes through, so `azp`
# is identical for user A and user B and only `sub` tells them apart.
_SHARED_CLIENT = "pipefy-mcp"
_TOKEN_A = "bearer-for-user-a"
_TOKEN_B = "bearer-for-user-b"
_SUBJECTS: Mapping[str, Any] = {_TOKEN_A: "user-a", _TOKEN_B: "user-b"}

# "the claim is not in the payload at all", which is a different input from a
# JSON `null` and worth distinguishing in a table of shapes.
_ABSENT = object()


class _TwoUserValidator:
    """Two bearers of the same OAuth client, differing only in `sub`.

    ``subjects`` maps each bearer to the ``sub`` value its payload carries, so a
    test can pick the shape it needs; :data:`_ABSENT` omits the claim entirely.
    """

    def __init__(self, subjects: Mapping[str, Any] = _SUBJECTS) -> None:
        self._subjects = subjects

    def validate(self, token: str) -> dict[str, Any]:
        if token not in self._subjects:
            raise ValueError("unknown token")
        claims: dict[str, Any] = {
            "azp": _SHARED_CLIENT,
            "iss": _ISSUER,
            "exp": _EXP,
        }
        sub = self._subjects[token]
        if sub is not _ABSENT:
            claims["sub"] = sub
        return claims


def _verifier(subjects: Mapping[str, Any] = _SUBJECTS) -> JwtTokenVerifier:
    return JwtTokenVerifier(_TwoUserValidator(subjects), resource=_RESOURCE)


def _build_http_app(subjects: Mapping[str, Any] = _SUBJECTS) -> Starlette:
    app = MCPServer(
        "session-ownership",
        token_verifier=_verifier(subjects),
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


@asynccontextmanager
async def _served_app(
    subjects: Mapping[str, Any] = _SUBJECTS,
) -> AsyncIterator[tuple[httpx.AsyncClient, Starlette]]:
    """The running app plus a client for it, for a test that needs both.

    The ``GET`` cases drive the app directly rather than through the client, so
    they need the app object; everything else goes through :func:`_served`.
    """
    http_app = _build_http_app(subjects)
    with anyio.fail_after(10):
        async with http_app.router.lifespan_context(http_app):
            transport = httpx.ASGITransport(app=http_app)
            async with httpx.AsyncClient(
                transport=transport, base_url=f"http://{_AUTHORITY}"
            ) as client:
                yield client, http_app


@asynccontextmanager
async def _served(
    subjects: Mapping[str, Any] = _SUBJECTS,
) -> AsyncIterator[httpx.AsyncClient]:
    """A client speaking to the real app over ASGI, lifespan and all."""
    async with _served_app(subjects) as (client, _):
        yield client


async def _open_session(client: httpx.AsyncClient, token: str) -> str:
    """Initialize a session as ``token`` and return its id."""
    created = await client.post(
        "/mcp", json=_initialize_body(), headers=_headers(token)
    )
    assert created.status_code == 200
    session_id = created.headers["mcp-session-id"]
    await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=_headers(token, session_id),
    )
    return session_id


async def _ping(
    client: httpx.AsyncClient, token: str, session_id: str
) -> httpx.Response:
    return await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
        headers=_headers(token, session_id),
    )


async def _attach_status(app: Starlette, token: str, session_id: str) -> int:
    """The status ``GET /mcp`` answers when ``token`` attaches to ``session_id``.

    This drives the ASGI app directly instead of going through the client above,
    because a successful attach is a stream that never ends and
    ``httpx.ASGITransport`` runs the app to completion before it yields a
    response. Reading the status off ``http.response.start`` and then cancelling
    is what lets the accepted case be asserted at all; the refused one would
    work either way.
    """
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        # The hand-built scope carries no Host of its own, and the SDK's
        # transport-security middleware answers 421 without one.
        "headers": [
            (key.encode(), value.encode())
            for key, value in {
                "host": _AUTHORITY,
                **_headers(token, session_id),
            }.items()
        ],
        "scheme": "http",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
    }
    started = anyio.Event()
    statuses: list[int] = []

    async def receive() -> dict[str, Any]:
        # A GET has no body, and the stream must not be told to disconnect.
        await anyio.sleep_forever()
        raise AssertionError("unreachable")

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            statuses.append(message["status"])
            started.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(app, scope, receive, send)
        await started.wait()
        task_group.cancel_scope.cancel()

    return statuses[0]


# --- the discriminating property, through the real session manager -----------


@pytest.mark.anyio
async def test_a_second_user_of_the_same_oauth_client_cannot_use_the_session() -> None:
    """User B presenting user A's session id is refused as if the session were gone.

    The whole point of the check: A and B share `azp`, so `client_id` alone cannot
    tell them apart. If the verifier stopped supplying `subject`, B's request would
    be served on A's session and this assertion would fail.
    """
    async with _served() as client:
        session_id = await _open_session(client, _TOKEN_A)
        hijacked = await _ping(client, _TOKEN_B, session_id)

    assert hijacked.status_code == 404
    # The refusal must not disclose that the session exists.
    assert hijacked.json()["error"]["message"] == "Session not found"


@pytest.mark.anyio
async def test_the_creating_user_keeps_using_their_own_session() -> None:
    """The control: the check rejects the other user, not every follow-up request."""
    async with _served() as client:
        session_id = await _open_session(client, _TOKEN_A)
        reused = await _ping(client, _TOKEN_A, session_id)

    assert reused.status_code == 200
    assert reused.json()["id"] == 2


@pytest.mark.anyio
async def test_a_second_user_cannot_attach_to_the_session_sse_stream() -> None:
    """The same refusal on ``GET /mcp``, which is a second way onto a session.

    ``POST`` is not the only reader of the ownership check: ``GET /mcp`` opens the
    standalone SSE stream, which is where server-initiated traffic (log
    notifications, elicitation, resource updates) would reach the caller. It is a
    distinct branch of the transport, so it is asserted rather than assumed to
    follow from the ``POST`` case.
    """
    async with _served_app() as (client, app):
        session_id = await _open_session(client, _TOKEN_A)
        attached = await _attach_status(app, _TOKEN_B, session_id)

    assert attached == 404


@pytest.mark.anyio
async def test_the_creating_user_can_attach_to_their_own_sse_stream() -> None:
    """The control for the attach case: the owner's own stream still opens."""
    async with _served_app() as (client, app):
        session_id = await _open_session(client, _TOKEN_A)
        attached = await _attach_status(app, _TOKEN_A, session_id)

    assert attached == 200


# --- the `sub` shapes, through the same manager -------------------------------


@pytest.mark.anyio
async def test_two_numeric_subjects_are_not_merged_into_one_principal() -> None:
    """A numeric `sub` must still tell two users apart.

    RFC 9068 asks for a string ``sub``, but an IdP that emits a number is still
    naming two different users, and the mapping must not throw that away. When
    ``subject`` dropped every non-string claim, both of these bearers mapped to
    ``subject=None`` and B was served on A's session.
    """
    async with _served({_TOKEN_A: 101, _TOKEN_B: 102}) as client:
        session_id = await _open_session(client, _TOKEN_A)
        hijacked = await _ping(client, _TOKEN_B, session_id)

    assert hijacked.status_code == 404


@pytest.mark.anyio
async def test_a_numeric_subject_is_not_merged_with_a_subjectless_bearer() -> None:
    """The same merge across shapes: a numeric `sub` is not the no-subject class."""
    async with _served({_TOKEN_A: 101, _TOKEN_B: _ABSENT}) as client:
        session_id = await _open_session(client, _TOKEN_A)
        hijacked = await _ping(client, _TOKEN_B, session_id)

    assert hijacked.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
async def test_a_blank_subject_is_refused_at_the_door(blank: str) -> None:
    """A blank `sub` never reaches session ownership: it is a 401, not a principal.

    An empty or whitespace-only ``sub`` is not a valid subject, so the bearer is
    rejected outright rather than normalized. Rejecting is what keeps a blank
    ``sub`` from joining the waived no-subject class, which is where mapping it to
    ``None`` would have put it -- and two blank-``sub`` bearers would then have
    shared a context.
    """
    async with _served({_TOKEN_A: blank}) as client:
        created = await client.post(
            "/mcp", json=_initialize_body(), headers=_headers(_TOKEN_A)
        )

    assert created.status_code == 401
    assert "mcp-session-id" not in created.headers


@pytest.mark.anyio
async def test_two_subjectless_bearers_of_one_client_share_one_context() -> None:
    """The waived case, pinned: no `sub` at all means no per-user discrimination.

    This is deliberate, not an oversight, and it is pinned so that a change to it
    is a decision someone makes on purpose. The identity precedence in
    ``_to_access_token`` exists to accept a bearer whose only identity claim is
    ``azp``/``client_id``; such a bearer names no end user, so the client identity
    is the whole principal and two of them are genuinely the same principal. It is
    also the degradation the SDK documents for an unsupplied component (see
    ``mcp.server.request_state.authenticated_principal``).

    Synthesizing a ``subject`` from ``jti`` or a hash of the bearer would make
    these two isolated, but at the cost of putting a credential id in the field
    every reader takes for an end user (``request_log_middleware`` logs it as
    ``sub``) and of breaking a caller's own session on every token refresh, since
    the refreshed credential would no longer match the principal that created the
    session.
    """
    async with _served({_TOKEN_A: _ABSENT, _TOKEN_B: _ABSENT}) as client:
        session_id = await _open_session(client, _TOKEN_A)
        shared = await _ping(client, _TOKEN_B, session_id)

    assert shared.status_code == 200


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
