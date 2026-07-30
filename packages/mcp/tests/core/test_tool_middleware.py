"""Unit tests for the tool-call middleware chain.

Covers the seam mechanics against a real ``MCPServer``: composition order,
short-circuit, exception propagation, the short-circuit envelope shape, the
pass-through of non-tool methods, and the argument-context build.

The chain is registered the way the composition root registers it, through
``MCPServer(middleware=[...])``, and driven through a real client rather than by
calling a handler directly. There is no longer a private handler slot to poke, so
these tests exercise the same path a caller does.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from _mcp_compat import create_connected_server_and_client_session as create_client
from mcp.server import ServerRequestContext
from mcp.server.mcpserver import MCPServer

from pipefy_mcp.core.tool_error_envelope import tool_error
from pipefy_mcp.core.tool_middleware import (
    ToolCallContext,
    build_tool_call_middleware,
    compose,
    context_from_server_request,
    short_circuit_error,
)


def _app(*middlewares) -> MCPServer:
    """An app with one tool and the chain registered as the composition root does."""
    adapter = build_tool_call_middleware(list(middlewares))
    app = MCPServer("test", middleware=[adapter] if adapter else None)

    @app.tool()
    async def echo(x: int) -> str:
        return f"got {x}"

    return app


def _bare_context(**arguments: object) -> ToolCallContext:
    """A minimal context for exercising the chain without a request scope."""
    return ToolCallContext(
        argument_keys=tuple(sorted(arguments)),
        identity=None,  # type: ignore[arg-type]
        request_id=None,
        tool_name="echo",
        arguments=dict(arguments) or None,
    )


def _server_request_context(
    method: str = "tools/call",
    params: dict | None = None,
    request_id: str = "m-1",
) -> ServerRequestContext:
    """A stdio-like per-message context: a request id, no HTTP request."""
    return ServerRequestContext(
        session=None,  # type: ignore[arg-type]
        lifespan_context=None,
        protocol_version="2025-11-25",
        method=method,
        params=params,
        request_id=request_id,
        request=None,
    )


async def _noop(ctx: ToolCallContext, call_next):
    """A pass-through middleware."""
    return await call_next(ctx)


async def _call_echo(app: MCPServer, **arguments: object):
    async with create_client(app) as client:
        return await client.call_tool("echo", dict(arguments))


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

    app = _app(recorder("A"), recorder("B"))

    result = asyncio.run(_call_echo(app, x=5))

    assert result.is_error is False
    assert "got 5" in result.content[0].text
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

    app = _app(deny, inner)

    result = asyncio.run(_call_echo(app, x=5))

    assert result.is_error is True
    assert reached_inner is False
    assert json.loads(result.content[0].text)["error"]["code"] == "DENIED"


@pytest.mark.unit
def test_non_tool_methods_pass_through_untouched():
    """A ``ServerMiddleware`` sees every method; only ``tools/call`` enters the chain.

    ``tools/list`` must reach the SDK handler without a ``ToolCallContext`` being
    built for it, otherwise every middleware would have to re-check the method and a
    logging consumer would emit a tool line per listing.
    """
    seen: list[str] = []

    async def recorder(ctx: ToolCallContext, call_next):
        seen.append(ctx.tool_name)
        return await call_next(ctx)

    app = _app(recorder)

    async def run() -> list[str]:
        async with create_client(app) as client:
            listed = await client.list_tools()
            await client.call_tool("echo", {"x": 1})
            return [tool.name for tool in listed.tools]

    names = asyncio.run(run())

    assert names == ["echo"]
    assert seen == ["echo"], "only the tools/call invocation should reach the chain"


@pytest.mark.unit
def test_chain_propagates_cancellation():
    """A ``CancelledError`` from the terminal propagates, not swallowed by the chain."""

    async def observer(ctx: ToolCallContext, call_next):
        return await call_next(ctx)

    async def boom(ctx: ToolCallContext):
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

    async def boom(ctx: ToolCallContext):
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

    envelope = json.loads(result.content[0].text)
    assert result.is_error is True
    assert result.structured_content == envelope
    assert envelope == {
        "success": False,
        "error": {"message": "quota exceeded", "code": "RATE_LIMITED"},
    }


@pytest.mark.unit
def test_short_circuit_matches_the_in_tool_error_envelope():
    """A short-circuit decodes to the same envelope a client reads from an in-tool error.

    A governance stop should carry the same ``tool_error`` payload an agent gets when a
    tool runs and fails, so the client needs no special-casing. The two are compared on
    the parsed envelope, not the bytes: MCPServer serializes a dict return through its own
    encoder (non-ASCII left raw, ``structured_content`` unset for a schema-less tool),
    while ``short_circuit_error`` uses ``json.dumps`` and fills ``structured_content``.
    Comparing decoded JSON pins the contract that matters and fails loud if either
    encoder or the envelope shape drifts, without false-alarming on cosmetics. The one
    intended divergence: the short-circuit is ``is_error=True`` (the tool never ran). The
    non-ASCII value below crosses the encoders' escaping difference to prove the point.
    """
    message, code, details = "blocked", "DENIED", {"reason": "quota (café)"}

    app = MCPServer("parity")

    @app.tool()
    async def failing() -> dict:
        return tool_error(message, code=code, details=details)

    async def run():
        async with create_client(app) as client:
            return await client.call_tool("failing", {})

    in_tool = asyncio.run(run())
    short_circuit = short_circuit_error(message, code=code, details=details)

    assert json.loads(in_tool.content[0].text) == json.loads(
        short_circuit.content[0].text
    )
    assert in_tool.is_error is False
    assert short_circuit.is_error is True


@pytest.mark.unit
def test_no_middleware_registers_nothing():
    """An empty list yields no ``ServerMiddleware``, so the default path stays bare.

    Replaces the old "install is a no-op" assertion. The chain is no longer installed
    over a handler, so the equivalent property is that the composition root has
    nothing to register and every inbound message skips the adapter entirely.
    """
    assert build_tool_call_middleware([]) is None
    assert build_tool_call_middleware([_noop]) is not None


@pytest.mark.unit
def test_context_exposes_bounded_argument_keys_without_values():
    """The context carries sorted argument keys, never the values."""
    ctx = context_from_server_request(
        _server_request_context(
            params={"name": "echo", "arguments": {"zeta": 1, "alpha": "secret-value"}},
        )
    )

    assert ctx.tool_name == "echo"
    assert ctx.argument_keys == ("alpha", "zeta")
    # No HTTP request in scope -> falls back to the JSON-RPC message id.
    assert ctx.request_id == "m-1"


@pytest.mark.unit
def test_context_tolerates_params_without_a_name():
    """A malformed ``tools/call`` still builds a context rather than raising.

    Middleware sees the raw params, so a client that omits ``name`` reaches the chain.
    Failing here would turn a client's bad request into a server fault, and a
    governance consumer counting calls needs to see it.
    """
    ctx = context_from_server_request(_server_request_context(params={}))

    assert ctx.tool_name == ""
    assert ctx.argument_keys == ()
    assert ctx.arguments is None
