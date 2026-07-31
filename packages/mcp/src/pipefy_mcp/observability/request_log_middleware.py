"""Pure-ASGI middleware that emits one structured JSON line per HTTP request."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any
from uuid import uuid4

from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from pipefy_mcp.observability.json_logging import (
    build_http_request_event,
    emit_structured_event,
)

ASGIApp = Callable[
    [
        MutableMapping[str, Any],
        Callable[..., Awaitable[Any]],
        Callable[..., Awaitable[None]],
    ],
    Awaitable[None],
]
ASGIReceive = Callable[[], Awaitable[MutableMapping[str, Any]]]
ASGISend = Callable[[MutableMapping[str, Any]], Awaitable[None]]

MCP_SESSION_ID_HEADER = "mcp-session-id"
REQUEST_ID_HEADERS = ("x-request-id", "x-correlation-id")


def _header_from_scope(scope: MutableMapping[str, Any], name: str) -> str | None:
    name_bytes = name.lower().encode("latin-1")
    for key, value in scope.get("headers", []):
        if key.lower() == name_bytes:
            return value.decode("latin-1")
    return None


def _header_from_response(headers: list[tuple[bytes, bytes]], name: str) -> str | None:
    name_bytes = name.lower().encode("latin-1")
    for key, value in headers:
        if key.lower() == name_bytes:
            return value.decode("latin-1")
    return None


def resolve_request_id(scope: MutableMapping[str, Any]) -> str:
    """Prefer an inbound correlation header; otherwise mint a server-side id.

    Honors ``x-request-id`` first, then ``x-correlation-id``. Empty or
    whitespace-only values are ignored so a proxy that sends a blank header
    does not suppress generation.
    """
    for name in REQUEST_ID_HEADERS:
        raw = _header_from_scope(scope, name)
        if raw is None:
            continue
        candidate = raw.strip()
        if candidate:
            return candidate
    return str(uuid4())


def _client_ip(scope: MutableMapping[str, Any]) -> str | None:
    client = scope.get("client")
    if not client:
        return None
    return client[0]


def _caller_identity(
    scope: MutableMapping[str, Any],
) -> tuple[str | None, str | None]:
    user = scope.get("user")
    if not isinstance(user, AuthenticatedUser):
        return None, None
    access_token = user.access_token
    # `subject` is the SDK's own field for the JWT `sub`, so every AccessToken
    # carries it and no narrowing to a subclass is needed.
    return access_token.subject, access_token.client_id


class RequestLogMiddleware:
    """Log one HTTP request as JSON without buffering the response body."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = time.perf_counter()
        request_id = resolve_request_id(scope)
        scope.setdefault("state", {})["request_id"] = request_id

        status: int | None = None
        response_session_id: str | None = None
        request_session_id = _header_from_scope(scope, MCP_SESSION_ID_HEADER)

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal status, response_session_id
            if message["type"] == "http.response.start":
                status = message["status"]
                response_session_id = _header_from_response(
                    message.get("headers", []),
                    MCP_SESSION_ID_HEADER,
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            sub, client_id = _caller_identity(scope)
            duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
            emit_structured_event(
                build_http_request_event(
                    method=scope["method"],
                    path=scope["path"],
                    status=status,
                    duration_ms=duration_ms,
                    client_ip=_client_ip(scope),
                    session_id=request_session_id or response_session_id,
                    request_id=request_id,
                    sub=sub,
                    client_id=client_id,
                )
            )
