"""Tests for the pure-ASGI HTTP request log middleware."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import anyio
import pytest
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from starlette.authentication import UnauthenticatedUser

from pipefy_mcp.observability.json_logging import (
    configure_observability_logging,
    reset_observability_logging,
)
from pipefy_mcp.observability.request_log_middleware import (
    RequestLogMiddleware,
    resolve_request_id,
)

ASGIApp = Callable[
    [
        MutableMapping[str, Any],
        Callable[..., Awaitable[Any]],
        Callable[..., Awaitable[None]],
    ],
    Awaitable[None],
]


def _http_scope(**overrides: Any) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"spec_version": "2.3", "version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"token=secret",
        "root_path": "",
        "scheme": "http",
        "headers": [],
        "client": ("127.0.0.1", 54321),
        "server": ("testserver", 80),
        "state": {},
    }
    scope.update(overrides)
    return scope


async def _noop_receive() -> dict[str, Any]:
    return {"type": "http.disconnect"}


async def _run_middleware(
    app: ASGIApp,
    scope: dict[str, Any],
    *,
    receive: Callable[[], Awaitable[dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def recording_send(message: dict[str, Any]) -> None:
        sent.append(message)

    middleware = RequestLogMiddleware(app)
    await middleware(scope, receive or _noop_receive, recording_send)
    return sent, scope


def _read_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
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
    configure_observability_logging()


@pytest.mark.anyio
async def test_emits_one_json_line_per_http_request(capsys):
    _configure_for_capture()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 201, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    scope = _http_scope()
    await _run_middleware(app, scope)

    lines = _read_log_lines(capsys)
    assert len(lines) == 1
    assert lines[0]["event"] == "http_request"
    assert lines[0]["method"] == "POST"
    assert lines[0]["path"] == "/mcp"
    assert lines[0]["status"] == 201
    assert lines[0]["client_ip"] == "127.0.0.1"
    assert lines[0]["request_id"] == scope["state"]["request_id"]
    assert "token=secret" not in json.dumps(lines[0])


@pytest.mark.anyio
async def test_non_http_scope_passthrough_without_logging(capsys):
    _configure_for_capture()

    async def app(scope, receive, send):
        await send({"type": "lifespan.startup", "state": {}})

    scope = {"type": "lifespan", "asgi": {"spec_version": "2.3", "version": "3.0"}}
    await _run_middleware(app, scope)

    assert _read_log_lines(capsys) == []


@pytest.mark.anyio
async def test_does_not_buffer_streaming_response_body(capsys):
    _configure_for_capture()
    first_chunk_sent = anyio.Event()
    unblock_app = anyio.Event()
    downstream_messages: list[dict[str, Any]] = []

    async def streaming_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send(
            {
                "type": "http.response.body",
                "body": b"partial",
                "more_body": True,
            }
        )
        first_chunk_sent.set()
        await unblock_app.wait()
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    scope = _http_scope()

    async def recording_send(message: dict[str, Any]) -> None:
        downstream_messages.append(message)

    middleware = RequestLogMiddleware(streaming_app)
    with anyio.fail_after(5):
        async with anyio.create_task_group() as tg:
            tg.start_soon(middleware, scope, _noop_receive, recording_send)
            await first_chunk_sent.wait()
            body_messages = [
                message
                for message in downstream_messages
                if message["type"] == "http.response.body"
            ]
            assert body_messages[0]["body"] == b"partial"
            unblock_app.set()

    assert len(_read_log_lines(capsys)) == 1


@pytest.mark.anyio
async def test_disconnect_mid_stream_still_emits_one_line(capsys):
    _configure_for_capture()

    async def streaming_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send(
            {
                "type": "http.response.body",
                "body": b"chunk",
                "more_body": True,
            }
        )
        message = await receive()
        assert message["type"] == "http.disconnect"

    async def disconnect_receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    await _run_middleware(streaming_app, _http_scope(), receive=disconnect_receive)

    lines = _read_log_lines(capsys)
    assert len(lines) == 1
    assert lines[0]["status"] == 200


@pytest.mark.anyio
async def test_send_failure_mid_stream_still_emits_one_line(capsys):
    """A send that raises after the first chunk (aborted socket) still logs once."""
    _configure_for_capture()
    sent_count = 0

    async def streaming_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"one", "more_body": True})
        await send({"type": "http.response.body", "body": b"two", "more_body": False})

    async def failing_send(message: dict[str, Any]) -> None:
        nonlocal sent_count
        sent_count += 1
        if sent_count == 3:
            raise RuntimeError("peer closed connection")

    middleware = RequestLogMiddleware(streaming_app)
    with pytest.raises(RuntimeError, match="peer closed connection"):
        await middleware(_http_scope(), _noop_receive, failing_send)

    lines = _read_log_lines(capsys)
    assert len(lines) == 1
    assert lines[0]["status"] == 200


@pytest.mark.anyio
async def test_crash_before_response_start_emits_status_null(capsys):
    _configure_for_capture()

    async def crashing_app(scope, receive, send):
        raise RuntimeError("boom before response.start")

    with pytest.raises(RuntimeError, match="boom before response.start"):
        await _run_middleware(crashing_app, _http_scope())

    lines = _read_log_lines(capsys)
    assert len(lines) == 1
    assert lines[0]["status"] is None


@pytest.mark.anyio
async def test_request_id_is_stored_on_scope_state(capsys):
    _configure_for_capture()

    async def app(scope, receive, send):
        assert "request_id" in scope["state"]
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    scope = _http_scope()
    await _run_middleware(app, scope)

    lines = _read_log_lines(capsys)
    assert lines[0]["request_id"] == scope["state"]["request_id"]


@pytest.mark.anyio
async def test_request_id_from_x_request_id_header(capsys):
    _configure_for_capture()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    scope = _http_scope(headers=[(b"x-request-id", b"upstream-req-1")])
    await _run_middleware(app, scope)

    lines = _read_log_lines(capsys)
    assert lines[0]["request_id"] == "upstream-req-1"
    assert scope["state"]["request_id"] == "upstream-req-1"


@pytest.mark.anyio
async def test_request_id_falls_back_to_x_correlation_id(capsys):
    _configure_for_capture()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    scope = _http_scope(headers=[(b"x-correlation-id", b"corr-abc")])
    await _run_middleware(app, scope)

    lines = _read_log_lines(capsys)
    assert lines[0]["request_id"] == "corr-abc"


@pytest.mark.anyio
async def test_x_request_id_wins_over_x_correlation_id(capsys):
    _configure_for_capture()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    scope = _http_scope(
        headers=[
            (b"x-correlation-id", b"corr-loses"),
            (b"x-request-id", b"req-wins"),
        ]
    )
    await _run_middleware(app, scope)

    lines = _read_log_lines(capsys)
    assert lines[0]["request_id"] == "req-wins"


def test_resolve_request_id_ignores_blank_headers_and_mints():
    scope = _http_scope(
        headers=[
            (b"x-request-id", b"   "),
            (b"x-correlation-id", b""),
        ]
    )
    minted = resolve_request_id(scope)
    assert minted
    assert minted.strip() == minted


@pytest.mark.anyio
async def test_sub_and_client_id_null_without_auth_context(capsys):
    _configure_for_capture()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    await _run_middleware(app, _http_scope())

    lines = _read_log_lines(capsys)
    assert lines[0]["sub"] is None
    assert lines[0]["client_id"] is None


@pytest.mark.anyio
async def test_sub_and_client_id_from_scope_user(capsys):
    _configure_for_capture()
    access_token = AccessToken(
        token="the-token",
        client_id="client-abc",
        scopes=["read"],
        subject="user-123",
    )

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    scope = _http_scope(
        user=AuthenticatedUser(access_token),
        headers=[(b"authorization", b"Bearer the-token")],
    )
    await _run_middleware(app, scope)

    lines = _read_log_lines(capsys)
    assert lines[0]["sub"] == "user-123"
    assert lines[0]["client_id"] == "client-abc"
    assert "the-token" not in json.dumps(lines)


@pytest.mark.anyio
async def test_unauthenticated_user_yields_null_identity(capsys):
    """The real auth stack sets UnauthenticatedUser, not a missing key."""
    _configure_for_capture()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    scope = _http_scope(user=UnauthenticatedUser())
    await _run_middleware(app, scope)

    lines = _read_log_lines(capsys)
    assert lines[0]["sub"] is None
    assert lines[0]["client_id"] is None
    assert lines[0]["status"] == 401


@pytest.mark.anyio
async def test_session_id_from_request_header(capsys):
    _configure_for_capture()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    scope = _http_scope(
        headers=[(b"mcp-session-id", b"request-session")],
    )
    await _run_middleware(app, scope)

    lines = _read_log_lines(capsys)
    assert lines[0]["session_id"] == "request-session"


@pytest.mark.anyio
async def test_session_id_falls_back_to_response_header(capsys):
    _configure_for_capture()

    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"mcp-session-id", b"response-session")],
            }
        )
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    await _run_middleware(app, _http_scope())

    lines = _read_log_lines(capsys)
    assert lines[0]["session_id"] == "response-session"


@pytest.mark.anyio
async def test_access_token_without_a_subject_yields_null_sub(capsys):
    """A token whose `sub` claim was absent logs a null sub, not an empty string."""
    _configure_for_capture()
    access_token = AccessToken(token="the-token", client_id="client-abc", scopes=[])

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    scope = _http_scope(
        user=AuthenticatedUser(access_token),
        headers=[(b"authorization", b"Bearer the-token")],
    )
    await _run_middleware(app, scope)

    lines = _read_log_lines(capsys)
    assert lines[0]["sub"] is None
    assert lines[0]["client_id"] == "client-abc"
    assert "the-token" not in json.dumps(lines)
