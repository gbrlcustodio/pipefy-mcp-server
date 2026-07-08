"""Unit tests for the tool-call middleware chain.

Covers the seam mechanics against a real FastMCP app: composition order,
short-circuit, exception propagation, the short-circuit envelope shape, the
once-per-app install, and the argument-context build.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager

import pytest
from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext

from pipefy_mcp.core.tool_middleware import (
    ToolCallContext,
    compose,
    context_from_request,
    install_tool_call_middleware,
    short_circuit_error,
)


def _app() -> FastMCP:
    app = FastMCP("test")

    @app.tool()
    async def echo(x: int) -> str:
        return f"got {x}"

    return app


def _call_tool_request(**arguments: object) -> types.CallToolRequest:
    return types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name="echo", arguments=arguments),
    )


def _bare_context(**arguments: object) -> ToolCallContext:
    """A minimal context for exercising the chain without a request scope."""
    return ToolCallContext(
        argument_keys=tuple(sorted(arguments)),
        identity=None,  # type: ignore[arg-type]
        request_id=None,
        req=_call_tool_request(**arguments),
    )


async def _noop(ctx: ToolCallContext, call_next):
    """A pass-through middleware, so an install actually wraps the handler."""
    return await call_next(ctx)


@contextmanager
def _message_scope(request_id: str = "req-1"):
    """Enter a request scope for one JSON-RPC message (stdio-like: no HTTP request)."""
    token = request_ctx.set(
        RequestContext(
            request_id=request_id,
            meta=None,
            session=None,  # type: ignore[arg-type]
            lifespan_context=None,
            request=None,
        )
    )
    try:
        yield
    finally:
        request_ctx.reset(token)


async def _invoke(app: FastMCP, req: types.CallToolRequest) -> types.ServerResult:
    """Run the app's (wrapped) CallToolRequest handler inside a request scope."""
    handler = app._mcp_server.request_handlers[types.CallToolRequest]
    with _message_scope():
        return await handler(req)


@pytest.mark.unit
def test_middleware_run_outer_to_inner_in_registration_order():
    """``[A, B]`` runs A, then B, then the tool, and unwinds in reverse."""
    trace: list[str] = []

    def recorder(label: str):
        async def mw(ctx: ToolCallContext, call_next):
            trace.append(f"{label}:before")
            result = await call_next(ctx)
            trace.append(f"{label}:after")
            return result

        return mw

    app = _app()
    install_tool_call_middleware(app, [recorder("A"), recorder("B")])

    result = asyncio.run(_invoke(app, _call_tool_request(x=5)))

    assert result.root.isError is False
    assert "got 5" in result.root.content[0].text
    assert trace == ["A:before", "B:before", "B:after", "A:after"]


@pytest.mark.unit
def test_middleware_short_circuits_without_running_the_tool():
    """Returning without awaiting ``call_next`` skips inner middleware and the tool."""
    reached_inner = False

    async def deny(ctx: ToolCallContext, call_next):
        return short_circuit_error("denied", code="DENIED")

    async def inner(ctx: ToolCallContext, call_next):
        nonlocal reached_inner
        reached_inner = True
        return await call_next(ctx)

    app = _app()
    install_tool_call_middleware(app, [deny, inner])

    result = asyncio.run(_invoke(app, _call_tool_request(x=5)))

    assert result.root.isError is True
    assert reached_inner is False
    assert json.loads(result.root.content[0].text)["error"]["code"] == "DENIED"


@pytest.mark.unit
def test_chain_propagates_cancellation():
    """A ``CancelledError`` from the terminal propagates, not swallowed by the chain."""

    async def observer(ctx: ToolCallContext, call_next):
        return await call_next(ctx)

    async def boom(req: types.CallToolRequest) -> types.ServerResult:
        raise asyncio.CancelledError

    chain = compose([observer], boom)

    async def run() -> None:
        await chain(_bare_context())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())


@pytest.mark.unit
def test_chain_propagates_arbitrary_exceptions():
    """``compose`` adds no try/except, so a terminal exception surfaces unchanged.

    Covers the ``Exception`` path (``CancelledError`` above covers ``BaseException``)
    that framework signals like ``UrlElicitationRequiredError`` travel: the chain
    must not intercept them.
    """

    class Boom(Exception):
        pass

    async def observer(ctx: ToolCallContext, call_next):
        return await call_next(ctx)

    async def boom(req: types.CallToolRequest) -> types.ServerResult:
        raise Boom("propagate me")

    chain = compose([observer], boom)

    async def run() -> None:
        await chain(_bare_context())

    with pytest.raises(Boom, match="propagate me"):
        asyncio.run(run())


@pytest.mark.unit
def test_short_circuit_error_shape():
    """The envelope is the canonical tool_error dict in both content and structured."""
    result = short_circuit_error("quota exceeded", code="RATE_LIMITED")
    root = result.root

    envelope = json.loads(root.content[0].text)
    assert root.isError is True
    assert root.structuredContent == envelope
    assert envelope == {
        "success": False,
        "error": {"message": "quota exceeded", "code": "RATE_LIMITED"},
    }


@pytest.mark.unit
def test_install_with_no_middleware_leaves_the_handler_untouched():
    """An empty chain is a no-op: FastMCP's own handler stays in place."""
    app = _app()
    original = app._mcp_server.request_handlers[types.CallToolRequest]
    install_tool_call_middleware(app, [])
    assert app._mcp_server.request_handlers[types.CallToolRequest] is original


@pytest.mark.unit
def test_reinstalling_on_the_same_app_raises():
    """Install is once-per-app: a second install fails loud instead of silently
    stacking or dropping middleware. Build the full list, install once."""

    async def other(ctx: ToolCallContext, call_next):
        return await call_next(ctx)

    app = _app()
    install_tool_call_middleware(app, [_noop])
    with pytest.raises(RuntimeError, match="already installed"):
        install_tool_call_middleware(app, [_noop, other])


@pytest.mark.unit
def test_install_wraps_each_app_independently():
    """A second app built in the same process wraps its own handler.

    Guards against a module- or class-global sentinel, which would wrap the first
    app and silently skip every later one.
    """
    app_one = _app()
    app_two = _app()
    install_tool_call_middleware(app_one, [_noop])
    install_tool_call_middleware(app_two, [_noop])

    handler_one = app_one._mcp_server.request_handlers[types.CallToolRequest]
    handler_two = app_two._mcp_server.request_handlers[types.CallToolRequest]
    assert handler_one is not handler_two


@pytest.mark.unit
def test_install_raises_when_handler_absent():
    """A missing CallToolRequest handler fails loud (SDK contract changed)."""
    app = _app()
    del app._mcp_server.request_handlers[types.CallToolRequest]
    with pytest.raises(RuntimeError, match="CallToolRequest handler missing"):
        install_tool_call_middleware(app, [_noop])


@pytest.mark.unit
def test_context_exposes_bounded_argument_keys_without_values():
    """The context carries sorted argument keys, never the values."""
    req = _call_tool_request(zeta=1, alpha="secret-value")
    with _message_scope(request_id="m-1"):
        ctx = context_from_request(req)

    assert ctx.tool_name == "echo"
    assert ctx.argument_keys == ("alpha", "zeta")
    # No HTTP request in scope -> falls back to the JSON-RPC message id.
    assert ctx.request_id == "m-1"
