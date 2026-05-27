"""Unit tests for ``pipefy_auth.bearer`` (Static, Callable, Refreshable adapters)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable

import httpx
import pytest

from pipefy_auth.bearer import (
    CallableBearerAuth,
    RefreshableBearerAuth,
    StaticBearerAuth,
)
from pipefy_auth.refresh import RefreshError


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


def _scripted_handler(
    statuses: list[int], seen: list[str]
) -> Callable[[httpx.Request], httpx.Response]:
    """Mock transport: returns ``statuses`` in order; records sent ``Authorization``."""
    iterator = iter(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization", ""))
        return httpx.Response(next(iterator))

    return handler


class TestRefreshableBearerAuthSync:
    @pytest.mark.unit
    def test_happy_path_401_then_refresh_then_retry(self) -> None:
        seen: list[str] = []
        client = httpx.Client(
            transport=httpx.MockTransport(_scripted_handler([401, 200], seen))
        )
        auth = RefreshableBearerAuth(
            token_provider=lambda: "OLD",
            force_refresh=lambda: "NEW",
        )

        response = client.get("https://example.test/", auth=auth)

        assert response.status_code == 200
        assert seen == ["Bearer OLD", "Bearer NEW"]

    @pytest.mark.unit
    def test_no_401_no_refresh_call(self) -> None:
        seen: list[str] = []
        refresh_calls: list[int] = []

        def force_refresh() -> str:
            refresh_calls.append(1)
            return "NEW"

        client = httpx.Client(
            transport=httpx.MockTransport(_scripted_handler([200], seen))
        )
        auth = RefreshableBearerAuth(
            token_provider=lambda: "OLD", force_refresh=force_refresh
        )

        response = client.get("https://example.test/", auth=auth)

        assert response.status_code == 200
        assert seen == ["Bearer OLD"]
        assert refresh_calls == []

    @pytest.mark.unit
    def test_force_refresh_exception_is_not_swallowed(self) -> None:
        seen: list[str] = []

        def force_refresh() -> str | None:
            raise RefreshError("invalid_grant", error_code="invalid_grant")

        client = httpx.Client(
            transport=httpx.MockTransport(_scripted_handler([401], seen))
        )
        auth = RefreshableBearerAuth(
            token_provider=lambda: "OLD", force_refresh=force_refresh
        )

        with pytest.raises(RefreshError):
            client.get("https://example.test/", auth=auth)
        assert seen == ["Bearer OLD"]

    @pytest.mark.unit
    def test_refresh_returns_none_lets_401_propagate(self) -> None:
        seen: list[str] = []
        client = httpx.Client(
            transport=httpx.MockTransport(_scripted_handler([401], seen))
        )
        auth = RefreshableBearerAuth(
            token_provider=lambda: "OLD",
            force_refresh=lambda: None,
        )

        response = client.get("https://example.test/", auth=auth)

        assert response.status_code == 401
        assert seen == ["Bearer OLD"]

    @pytest.mark.unit
    def test_refresh_returns_same_token_does_not_retry(self) -> None:
        seen: list[str] = []
        client = httpx.Client(
            transport=httpx.MockTransport(_scripted_handler([401], seen))
        )
        auth = RefreshableBearerAuth(
            token_provider=lambda: "OLD",
            force_refresh=lambda: "OLD",
        )

        response = client.get("https://example.test/", auth=auth)

        assert response.status_code == 401
        assert seen == ["Bearer OLD"]

    @pytest.mark.unit
    def test_retry_also_401_does_not_loop(self) -> None:
        seen: list[str] = []
        client = httpx.Client(
            transport=httpx.MockTransport(_scripted_handler([401, 401], seen))
        )
        auth = RefreshableBearerAuth(
            token_provider=lambda: "OLD",
            force_refresh=lambda: "NEW",
        )

        response = client.get("https://example.test/", auth=auth)

        assert response.status_code == 401
        assert seen == ["Bearer OLD", "Bearer NEW"]


class TestRefreshableBearerAuthAsync:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_happy_path_401_then_refresh_then_retry(self) -> None:
        seen: list[str] = []
        transport = httpx.MockTransport(_scripted_handler([401, 200], seen))
        auth = RefreshableBearerAuth(
            token_provider=lambda: "OLD",
            force_refresh=lambda: "NEW",
        )

        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.get("https://example.test/", auth=auth)

        assert response.status_code == 200
        assert seen == ["Bearer OLD", "Bearer NEW"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_force_refresh_exception_is_not_swallowed(self) -> None:
        seen: list[str] = []
        transport = httpx.MockTransport(_scripted_handler([401], seen))

        def force_refresh() -> str | None:
            raise RefreshError("invalid_grant", error_code="invalid_grant")

        auth = RefreshableBearerAuth(
            token_provider=lambda: "OLD", force_refresh=force_refresh
        )

        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(RefreshError):
                await client.get("https://example.test/", auth=auth)
        assert seen == ["Bearer OLD"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retry_also_401_does_not_loop(self) -> None:
        seen: list[str] = []
        transport = httpx.MockTransport(_scripted_handler([401, 401], seen))
        auth = RefreshableBearerAuth(
            token_provider=lambda: "OLD",
            force_refresh=lambda: "NEW",
        )

        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.get("https://example.test/", auth=auth)

        assert response.status_code == 401
        assert seen == ["Bearer OLD", "Bearer NEW"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_401s_serialize_under_async_lock(self) -> None:
        """Under async fan-out, ``force_refresh`` runs serially — never two
        threads inside it at once. Probed with ``threading.Barrier(parties=3)``:
        without the lock all three threads rendezvous, with the lock only one
        ever arrives and the barrier raises ``BrokenBarrierError``. Three
        refresh calls (not one) pins the serialize-but-don't-coalesce contract;
        coalescing racing refreshes is out of scope for this class.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            if request.headers.get("Authorization") == "Bearer NEW":
                return httpx.Response(200)
            return httpx.Response(401)

        barrier = threading.Barrier(parties=3, timeout=0.5)
        state_lock = threading.Lock()
        concurrent_rendezvous = 0
        serialized_timeouts = 0
        refresh_calls = 0

        def force_refresh() -> str:
            nonlocal concurrent_rendezvous, serialized_timeouts, refresh_calls
            with state_lock:
                refresh_calls += 1
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                with state_lock:
                    serialized_timeouts += 1
                return "NEW"
            with state_lock:
                concurrent_rendezvous += 1
            return "NEW"

        transport = httpx.MockTransport(handler)
        auth = RefreshableBearerAuth(
            token_provider=lambda: "OLD",
            force_refresh=force_refresh,
        )

        async with httpx.AsyncClient(transport=transport) as client:
            results = await asyncio.gather(
                client.get("https://example.test/", auth=auth),
                client.get("https://example.test/", auth=auth),
                client.get("https://example.test/", auth=auth),
            )

        assert all(r.status_code == 200 for r in results)
        assert concurrent_rendezvous == 0, (
            "async lock must prevent concurrent force_refresh entry; "
            f"{concurrent_rendezvous} thread(s) reached the barrier rendezvous"
        )
        assert serialized_timeouts == 3, (
            "every force_refresh call must time out alone at the barrier — "
            f"got {serialized_timeouts}"
        )
        assert refresh_calls == 3, (
            "serialize-not-coalesce: three concurrent 401s drive three refreshes"
        )
