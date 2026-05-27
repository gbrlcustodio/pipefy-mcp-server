"""``httpx.Auth`` adapters that attach ``Authorization: Bearer …`` headers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Generator

from httpx import Auth, Request, Response


class StaticBearerAuth(Auth):
    """Attach a fixed ``Authorization: Bearer …`` header."""

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: Request) -> Generator[Request, Response, None]:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


class CallableBearerAuth(Auth):
    """Attach ``Authorization: Bearer …`` from a token provider invoked per request.

    The provider is re-called on every request so transparent rotation (e.g. a
    keychain-backed refresh in :func:`ensure_fresh_session`) is observed without
    rebuilding the SDK client. The async path serializes concurrent calls so a
    single request triggers at most one refresh under async fan-out.
    """

    def __init__(self, token_provider: Callable[[], str]) -> None:
        self._token_provider = token_provider
        self._async_lock = asyncio.Lock()

    def auth_flow(self, request: Request) -> Generator[Request, Response, None]:
        request.headers["Authorization"] = f"Bearer {self._token_provider()}"
        yield request

    async def async_auth_flow(
        self, request: Request
    ) -> AsyncGenerator[Request, Response]:
        async with self._async_lock:
            token = await asyncio.to_thread(self._token_provider)
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


class RefreshableBearerAuth(Auth):
    """Per-request bearer + reactive refresh-on-401 retry.

    Pairs the per-request token rotation behaviour of :class:`CallableBearerAuth`
    with a 401 safety net: when an API call returns 401, ``force_refresh`` is
    invoked to obtain a new bearer and the request is retried exactly once. If
    it returns ``None`` or the same token, the 401 propagates so callers surface
    a "session expired, re-login" error instead of looping. ``force_refresh`` is
    trusted to return ``str | None`` — translating an IdP failure (``RefreshError``)
    into ``None`` is the wiring's job, not this class's.

    The eager refresh path (``token_provider`` calling
    :func:`pipefy_auth.refresh.ensure_fresh_session`) still handles the common
    "token expired by our clock" case. This class fills the gap eager refresh
    cannot see — IdP-side revocation, and the narrow race between the eager
    check and the API call.

    Concurrency model: under async fan-out, the internal lock **serializes**
    both eager token reads (``token_provider``) and reactive refreshes
    (``force_refresh``) — three concurrent 401s run three refreshes
    back-to-back, not one shared refresh. Coalescing racing refreshes is
    out of scope here; it's the responsibility of the refresh-token grant
    path.
    """

    def __init__(
        self,
        *,
        token_provider: Callable[[], str],
        force_refresh: Callable[[], str | None],
    ) -> None:
        self._token_provider = token_provider
        self._force_refresh = force_refresh
        self._async_lock = asyncio.Lock()

    def auth_flow(self, request: Request) -> Generator[Request, Response, None]:
        token = self._token_provider()
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code != 401:
            return
        new_token = self._force_refresh()
        if new_token is None or new_token == token:
            return
        request.headers["Authorization"] = f"Bearer {new_token}"
        yield request

    async def async_auth_flow(
        self, request: Request
    ) -> AsyncGenerator[Request, Response]:
        async with self._async_lock:
            token = await asyncio.to_thread(self._token_provider)
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code != 401:
            return
        async with self._async_lock:
            new_token = await asyncio.to_thread(self._force_refresh)
        if new_token is None or new_token == token:
            return
        request.headers["Authorization"] = f"Bearer {new_token}"
        yield request


__all__ = [
    "CallableBearerAuth",
    "RefreshableBearerAuth",
    "StaticBearerAuth",
]
