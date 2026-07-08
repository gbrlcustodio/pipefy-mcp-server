from __future__ import annotations

import logging
import textwrap
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.core.runtime import McpRuntime
from pipefy_mcp.core.tool_middleware import install_tool_call_middleware
from pipefy_mcp.settings import Settings
from pipefy_mcp.tools.registry import ToolRegistry
from pipefy_mcp.tools.validation_envelope import install_pipefy_validation_envelope

logger = logging.getLogger(__name__)

PIPEFY_INSTRUCTIONS = textwrap.dedent("""
    You are connected to a Pipefy MCP server for managing Kanban-style workflow processes.
    """).strip()

# Hosts that keep the server reachable only from the local machine. The HTTP
# transport refuses to bind anywhere else (a routable interface or 0.0.0.0)
# until the DNS-rebinding host/Origin allowlist lands; see
# _assert_safe_http_bind.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _make_lifespan(
    runtime: McpRuntime,
) -> Callable[[FastMCP], AbstractAsyncContextManager[McpRuntime]]:
    """Build the FastMCP lifespan bound to the one app-scoped ``runtime``.

    Following the FastMCP lifespan contract, the lifespan owns resources only: it
    yields the runtime as the request ``lifespan_context``. Tools resolve the live
    client per request from that context (see
    :func:`pipefy_mcp.tools.tool_context.get_pipefy_client`), so both transports
    must run a lifespan for tools to find a client.

    The one runtime is built once at server construction (which builds its engine)
    and captured here. Streamable HTTP re-enters this context manager per session;
    each entry yields the same already-wired runtime, so every session shares one
    engine and opens its own cheap per-request session. See AGENTS.md for the fuller
    rationale.

    Tools are registered once, up front, by :func:`_register_pipefy_tools`, never
    here, so re-entry cannot race the tool table.
    """

    @asynccontextmanager
    async def lifespan(_app: FastMCP) -> AsyncIterator[McpRuntime]:
        logger.info(
            "PIPEFY_MCP_UNIFIED_ENVELOPE=%s",
            "enabled" if runtime.settings.mcp.unified_envelope else "disabled",
        )
        yield runtime

    return lifespan


def _register_pipefy_tools(app: FastMCP, *, remote_mode: bool) -> None:
    """Register every Pipefy tool on ``app`` exactly once, at construction.

    Shared by both transports. Tools take no client at registration: each opens a
    session per request from the lifespan context (see
    :func:`pipefy_mcp.tools.tool_context.get_pipefy_client`), so registration is
    decoupled from how or when the runtime builds its engine. Registration never
    repeats, so there is no repeat-visit bookkeeping to maintain.
    """
    install_pipefy_validation_envelope()
    registry = ToolRegistry(mcp=app)
    registry.check_for_name_collisions()
    registry.register_tools()
    registry.apply_remote_profile(remote_mode=remote_mode)


def build_pipefy_mcp_server(settings: Settings) -> FastMCP:
    """Build the FastMCP app with its tools registered once, before serving.

    Reads everything from the resolved ``settings`` the composition root
    (:func:`run_server`) hands in: the ``remote`` profile selects the default-deny
    remote-safe tool surface, and ``settings.mcp.host`` / ``settings.mcp.port`` give
    the HTTP bind (they matter only for the HTTP transport; stdio ignores them).

    The one app-scoped :class:`McpRuntime` is built via
    :meth:`McpRuntime.for_profile`, which owns both the outbound identity and (under
    ``remote``) the inbound resource-server ``(verifier, auth)`` pair. When that pair
    is present FastMCP validates the inbound bearer per request and serves the
    resource-server metadata; when it is ``None`` (stdio, or a ``local`` HTTP
    profile) the app has no inbound auth. The lifespan is bound to that runtime; only
    the transport ``run`` differs.
    """
    runtime = McpRuntime.for_profile(settings)
    verifier, auth = runtime.inbound_auth or (None, None)
    app = FastMCP(
        "pipefy",
        instructions=PIPEFY_INSTRUCTIONS,
        lifespan=_make_lifespan(runtime),
        host=settings.mcp.host,
        port=settings.mcp.port,
        token_verifier=verifier,
        auth=auth,
    )
    _register_pipefy_tools(app, remote_mode=settings.mcp.profile == "remote")
    # Wrap the tool-call handler with the runtime's registered middleware chain.
    # Both transports serve this app, so tool calls over stdio and HTTP alike run
    # through the chain; the built-in logger is seeded per profile (see
    # McpRuntime.for_profile) and this is a no-op when nothing is registered.
    install_tool_call_middleware(app, runtime.tool_middlewares)
    return app


def _assert_safe_http_bind(*, host: str) -> None:
    """Refuse to bind the HTTP transport to a non-loopback host.

    The HTTP transport is restricted to loopback for now. The resource-server
    profile carries per-request on-behalf-of identity (each call runs as the
    validated caller, not a single startup identity), so inbound identity is not
    the constraint; the constraint is DNS-rebinding protection, the configurable
    host / Origin allowlist. (The filesystem tools, e.g. the attachment uploads,
    also only make sense on loopback, where the server shares the client's disk;
    remote-safe file inputs are separate follow-up work.)

    Off-loopback binding stays off until that allowlist lands; see
    experiments/hosted-obo/RFC-OUTLINE.md.
    """
    if host in _LOOPBACK_HOSTS:
        return
    raise RuntimeError(
        f"Refusing to serve over HTTP on a non-loopback host ({host}). The HTTP "
        f"transport is restricted to loopback (127.0.0.1/localhost/::1) until "
        f"the hosted on-behalf-of profile lands."
    )


def run_server(settings: Settings) -> None:
    """Run the Pipefy MCP server. The single serve entry point for both transports.

    Takes a fully-resolved :class:`Settings`. The console entry point resolves the
    launch flags through :func:`resolve_mcp_settings` (argv beats ``PIPEFY_MCP_*``,
    filling the profile-derived transport default and rejecting an incompatible
    pair) and passes the result, so this module reads no process globals.

    ``settings.mcp.transport == "stdio"`` speaks MCP over stdio; ``"http"`` serves
    over Streamable HTTP on ``host``/``port``, restricted to a loopback bind until
    the hosted on-behalf-of profile lands (see :func:`_assert_safe_http_bind`).

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
    profile has no resource server). They differ only in the transport ``run`` and
    HTTP's bind concerns.
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
    _assert_safe_http_bind(host=mcp.host)

    build_pipefy_mcp_server(settings).run("streamable-http")
