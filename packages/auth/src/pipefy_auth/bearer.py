"""``httpx.Auth`` adapters that attach ``Authorization: Bearer …`` headers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator
from typing import AsyncGenerator

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


__all__ = [
    "CallableBearerAuth",
    "StaticBearerAuth",
]
