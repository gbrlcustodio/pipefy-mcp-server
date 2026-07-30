from __future__ import annotations

import logging
import textwrap
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING

import anyio
from mcp.server.mcpserver import MCPServer

if TYPE_CHECKING:
    from mcp.server.transport_security import TransportSecuritySettings

from pipefy_mcp import __version__ as pipefy_mcp_version
from pipefy_mcp.core.runtime import McpRuntime
from pipefy_mcp.core.tool_middleware import (
    ToolCallMiddleware,
    build_tool_call_middleware,
)
from pipefy_mcp.core.transport_security import transport_security_for
from pipefy_mcp.observability.json_logging import configure_observability_logging
from pipefy_mcp.observability.tool_log_middleware import tool_log_middleware
from pipefy_mcp.observability.wiring import wire_hosted_observability
from pipefy_mcp.settings import Settings
from pipefy_mcp.tools.registry import ToolRegistry
from pipefy_mcp.tools.toolsets import resolve_selection, wants_power
from pipefy_mcp.tools.validation_envelope import install_pipefy_validation_envelope

logger = logging.getLogger(__name__)

PIPEFY_INSTRUCTIONS = textwrap.dedent("""
    You are connected to a Pipefy MCP server for managing Kanban-style workflow processes.
    """).strip()


def _make_lifespan(
    runtime: McpRuntime,
) -> Callable[[MCPServer], AbstractAsyncContextManager[McpRuntime]]:
    """Build the SDK lifespan bound to the one app-scoped ``runtime``.

    Following the SDK lifespan contract, the lifespan owns resources only: it
    yields the runtime as the request ``lifespan_context``. Tools resolve the live
    client per request from that context (see
    :func:`pipefy_mcp.tools.tool_context.get_pipefy_client`), so both transports
    must run a lifespan for tools to find a client.

    The one runtime is built once at server construction (which builds its engine)
    and captured here. Under 2.0 Streamable HTTP enters this context manager once, at
    session-manager startup, rather than per session; either way every entry yields
    the same already-wired runtime, so all sessions share one engine and each opens
    its own cheap per-request session. See AGENTS.md for the fuller rationale.

    Tools are registered once, up front, by :func:`_register_pipefy_tools`, never
    here, so registration cannot race the tool table regardless of how often the
    lifespan runs.
    """

    @asynccontextmanager
    async def lifespan(_app: MCPServer) -> AsyncIterator[McpRuntime]:
        logger.info(
            "PIPEFY_MCP_UNIFIED_ENVELOPE=%s",
            "enabled" if runtime.unified_envelope else "disabled",
        )
        yield runtime

    return lifespan


def _register_pipefy_tools(
    app: MCPServer, *, remote_mode: bool, toolsets: str | None
) -> None:
    """Register every Pipefy tool on ``app`` exactly once, at construction.

    Shared by both transports. Tools take no client at registration: each opens a
    session per request from the lifespan context (see
    :func:`pipefy_mcp.tools.tool_context.get_pipefy_client`), so registration is
    decoupled from how or when the runtime builds its engine. Registration never
    repeats, so there is no repeat-visit bookkeeping to maintain.

    The remote floor then the toolset selection are applied in that order, so a
    ``toolsets`` selection narrows within the surviving surface and never widens it.
    The ``power`` selection is a distinct branch: rather than narrow by domain, it
    hides the curated tools behind the catalog meta-tools (still post-floor).
    """
    install_pipefy_validation_envelope()
    registry = ToolRegistry(mcp=app)
    registry.check_for_name_collisions()
    registry.register_tools()
    registry.apply_remote_profile(remote_mode=remote_mode)
    if wants_power(toolsets):
        # Validate the spec before applying power: apply_power_profile does not call
        # resolve_selection, so without this an unknown token (e.g. "power,typo")
        # would silently start the server, unlike the fail-closed domain path.
        resolve_selection(toolsets)
        registry.apply_power_profile()
    else:
        registry.apply_toolset_selection(toolsets)


def default_tool_middlewares(settings: Settings) -> list[ToolCallMiddleware]:
    """The built-in tool-call middleware to seed for the resolved profile.

    Structured tool-call logging is on by default under the hosted ``remote``
    profile, where operators rely on it to attribute activity. This is a default,
    not a capability boundary: the chain installs on every profile, so any
    deployment can register its own middleware, and this could later become a
    config toggle a local deployment opts into. Deciding the seed here, at the
    composition root, keeps the runtime free of any dependency on a concrete
    middleware.
    """
    if settings.mcp.profile == "remote":
        return [tool_log_middleware]
    return []


def build_pipefy_mcp_server(
    settings: Settings,
    extra_tool_middlewares: Sequence[ToolCallMiddleware] = (),
) -> MCPServer:
    """Build the MCP app with its tools registered once, before serving.

    Reads everything from the resolved ``settings`` the composition root
    (:func:`run_server`) hands in: the ``remote`` profile selects the default-deny
    remote-safe tool surface.

    The bind host/port and the DNS-rebinding allowlist are NOT set here. The SDK
    takes them per transport, on ``run()`` / ``streamable_http_app()``, so they
    travel with the serving call (:func:`_serve_streamable_http`) rather than with
    the app. Only the HTTP transport has anything to apply them to.

    ``extra_tool_middlewares`` is the public registration seam for a consumer of this
    builder (a hosted serving layer that wants per-tool metrics, say): the chain is
    composed once and registered at construction, so a consumer folds its middleware
    in here. The built-in middleware runs outer to the consumer's, so the default
    observability layer records every call including those a consumer's middleware
    short-circuits.

    The one app-scoped :class:`McpRuntime` is built via
    :meth:`McpRuntime.for_profile`, which owns both the outbound identity and (under
    ``remote``) the inbound resource-server ``(verifier, auth)`` pair. When that pair
    is present the SDK validates the inbound bearer per request and serves the
    resource-server metadata; when it is ``None`` (stdio, or a ``local`` HTTP
    profile) the app has no inbound auth. The lifespan is bound to that runtime; only
    the transport ``run`` differs.
    """
    runtime = McpRuntime.for_profile(settings)
    verifier, auth = runtime.inbound_auth or (None, None)
    # One ServerMiddleware carrying the built-in chain plus any consumer middleware,
    # registered at construction because the SDK takes middleware on the constructor.
    # Both transports serve this app, so tool calls over stdio and HTTP alike run
    # through the chain; the list is empty (and the middleware None) by default.
    tool_middleware = build_tool_call_middleware(
        [*default_tool_middlewares(settings), *extra_tool_middlewares]
    )
    app = MCPServer(
        "pipefy",
        version=pipefy_mcp_version,
        instructions=PIPEFY_INSTRUCTIONS,
        lifespan=_make_lifespan(runtime),
        log_level=settings.mcp.log_level,
        token_verifier=verifier,
        auth=auth,
        middleware=[tool_middleware] if tool_middleware else None,
    )
    _register_pipefy_tools(
        app,
        remote_mode=settings.mcp.profile == "remote",
        toolsets=settings.mcp.toolsets,
    )
    return app


async def _serve_streamable_http(
    app: MCPServer,
    settings: Settings,
    transport_security: TransportSecuritySettings | None,
) -> None:
    """Serve Streamable HTTP with hosted observability middleware wired in.

    The structured emitter is configured here, not in :func:`run_server`, so the
    stdio path never installs it. Structured lines go to stderr (not the JSON-RPC
    stdout wire); keeping configuration off the stdio path still avoids arming a
    process-global handler that local installs do not need.

    ``transport_security`` (the DNS-rebinding allowlist) and the bind ``host`` reach
    the SDK here rather than at construction, because the SDK takes both on
    ``streamable_http_app()``. Passing the same ``host`` uvicorn binds keeps the
    allowlist's loopback default aligned with the interface actually served.
    """
    import uvicorn

    configure_observability_logging()
    mcp = settings.mcp
    http_app = wire_hosted_observability(
        app, host=mcp.host, transport_security=transport_security
    )
    config = uvicorn.Config(
        http_app,
        host=mcp.host,
        port=mcp.port,
        log_level=mcp.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


def run_server(settings: Settings) -> None:
    """Run the Pipefy MCP server. The single serve entry point for both transports.

    Takes a fully-resolved :class:`Settings`. The console entry point resolves the
    launch flags through :func:`resolve_mcp_settings` (argv beats ``PIPEFY_MCP_*``,
    filling the profile-derived transport default and rejecting an incompatible
    pair) and passes the result, so this module reads no process globals.

    ``settings.mcp.transport == "stdio"`` speaks MCP over stdio; ``"http"`` serves
    over Streamable HTTP on ``host``/``port``.

    ``settings.mcp.profile == "remote"`` selects the default-deny remote-safe tool
    surface and validates an inbound bearer per request; it requires a configured
    resource server (:meth:`McpRuntime.for_profile` fails fast otherwise). ``local``
    registers every tool and runs as the one startup credential.

    The server is built here, at startup rather than at import. Building registers
    every tool and reads the profile, so building at import would make
    ``--version``/``--help`` pay the full cost and turn any registration error into
    an import failure.

    Both transports build the same app through :func:`build_pipefy_mcp_server`,
    which builds the app-scoped runtime via :meth:`McpRuntime.for_profile` (owning
    the inbound resource-server pair for ``remote`` and failing fast when that
    profile has no resource server). They differ only in the transport ``run``.
    """
    mcp = settings.mcp

    if mcp.transport == "stdio":
        logger.info("Starting Pipefy MCP server over stdio (profile=%s)", mcp.profile)
        build_pipefy_mcp_server(settings).run()
        return

    # The remote profile validates a per-request bearer; a local server over
    # loopback HTTP trusts its peer and wires no inbound auth. The runtime owns that
    # decision (and the fail-fast when remote has no resource server), so it holds
    # for a serving remote server: profile == "remote" is exactly when inbound
    # validation is active.
    logger.info(
        "Starting Pipefy MCP server over HTTP on %s:%d (profile=%s, resource_server=%s)",
        mcp.host,
        mcp.port,
        mcp.profile,
        "active" if mcp.profile == "remote" else "inactive",
    )

    # Bind safety is enforced at the settings boundary (McpSettings._enforce_bind_safety);
    # host/port arrive already vetted, so there is nothing to re-check here.
    anyio.run(
        _serve_streamable_http,
        build_pipefy_mcp_server(settings),
        settings,
        transport_security_for(settings),
    )
