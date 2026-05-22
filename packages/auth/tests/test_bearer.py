"""Unit tests for ``pipefy_auth.bearer`` (Static + Callable bearer adapters)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from pipefy_auth.bearer import CallableBearerAuth, StaticBearerAuth


@pytest.mark.unit
def test_static_bearer_sets_authorization_header():
    auth = StaticBearerAuth("ABC")
    request = httpx.Request("GET", "https://example.test/")
    flow = auth.auth_flow(request)
    sent = next(flow)
    assert sent.headers["Authorization"] == "Bearer ABC"


@pytest.mark.unit
def test_callable_bearer_invokes_provider_per_request_sync():
    tokens = iter(["T1", "T2", "T3"])
    auth = CallableBearerAuth(lambda: next(tokens))
    seen = []
    for _ in range(3):
        request = httpx.Request("GET", "https://example.test/")
        next(auth.auth_flow(request))
        seen.append(request.headers["Authorization"])
    assert seen == ["Bearer T1", "Bearer T2", "Bearer T3"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_callable_bearer_async_serializes_provider_calls():
    """The async lock means two concurrent ``async_auth_flow`` calls do not
    interleave the provider invocations."""
    call_order: list[str] = []

    def provider() -> str:
        call_order.append("call")
        return "TOK"

    auth = CallableBearerAuth(provider)

    async def one_call() -> str:
        request = httpx.Request("GET", "https://example.test/")
        gen = auth.async_auth_flow(request)
        await gen.__anext__()
        await gen.aclose()
        return request.headers["Authorization"]

    headers = await asyncio.gather(one_call(), one_call(), one_call())
    assert headers == ["Bearer TOK"] * 3
    assert len(call_order) == 3
