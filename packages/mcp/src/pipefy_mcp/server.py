from __future__ import annotations

import logging
import textwrap
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from mcp.server.fastmcp import FastMCP

from pipefy_mcp.auth import (
    RequestContextBearerAuth,
    ResourceServerAuth,
    build_resource_server_auth,
)
from pipefy_mcp.core.runtime import (
    AuthSource,
    McpRuntime,
    RequestScopedIdentity,
    StartupIdentity,
)
from pipefy_mcp.settings import Settings, resolve_mcp_settings, settings
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

    The one runtime is built once at server construction (which wires its client)
    and captured here. Streamable HTTP re-enters this context manager per session;
    each entry yields the same already-wired runtime, so every session shares one
    client and there is nothing to rebuild. See AGENTS.md for the fuller rationale.

    Tools are registered once, up front, by :func:`_register_pipefy_tools`, never
    here, so re-entry cannot race the tool table.
    """

    @asynccontextmanager
    async def lifespan(_app: FastMCP) -> AsyncIterator[McpRuntime]:
        logger.info(
            "PIPEFY_MCP_UNIFIED_ENVELOPE=%s",
            "enabled" if settings.mcp.unified_envelope else "disabled",
        )
        yield runtime

    return lifespan


def _select_auth_source(
    settings: Settings, resource_server: ResourceServerAuth | None
) -> AuthSource:
    """Parse the transport profile into the shared client's identity source.

    The resource-server profile validates a per-request bearer, so the shared
    client acts on behalf of each caller (:class:`RequestScopedIdentity`, reading
    the request context per call). Without it (stdio, or the disabled HTTP
    profile) there is no inbound identity, so the one startup credential is
    resolved from settings (and fails fast when none is configured); see
    :meth:`StartupIdentity.from_configured_credential`.
    """
    if resource_server is not None:
        return RequestScopedIdentity(RequestContextBearerAuth())
    return StartupIdentity.from_configured_credential(settings)


def _register_pipefy_tools(app: FastMCP, *, remote_mode: bool) -> None:
    """Register every Pipefy tool on ``app`` exactly once, at construction.

    Shared by both transports. Tools take no client at registration: each
    resolves the live client per request from the lifespan context (see
    :func:`pipefy_mcp.tools.tool_context.get_pipefy_client`), so registration is
    decoupled from how or when the runtime wires its client. Registration never
    repeats, so there is no repeat-visit bookkeeping to maintain.
    """
    install_pipefy_validation_envelope()
    registry = ToolRegistry(mcp=app)
    registry.check_for_name_collisions()
    registry.register_tools()
    registry.apply_remote_profile(remote_mode=remote_mode)


def _resolve_bind(host: str | None, port: int | None) -> tuple[str, int]:
    """Fill an unset HTTP bind host/port from ``PIPEFY_MCP_HOST`` / ``PIPEFY_MCP_PORT``.

    Used by :func:`build_pipefy_mcp_server` for a direct call that passes no
    host/port (e.g. tests). The serve path resolves them earlier, in
    :func:`run_server` via :func:`resolve_mcp_settings`, and passes them in.
    """
    return (
        host if host is not None else settings.mcp.host,
        port if port is not None else settings.mcp.port,
    )


def build_pipefy_mcp_server(
    *,
    remote_mode: bool | None = None,
    host: str | None = None,
    port: int | None = None,
    resource_server: ResourceServerAuth | None = None,
) -> FastMCP:
    """Build the FastMCP app with its tools registered once, before serving.

    Used by both transports. It builds the one app-scoped :class:`McpRuntime`
    (its identity source chosen by :func:`_select_auth_source` from the profile)
    and binds the lifespan to it; only the transport ``run`` differs.
    ``remote_mode`` (the default-deny remote-safe tool surface) defaults to whether
    the configured profile is ``remote``; pass an explicit value to override (used
    by tests). ``host``/``port`` default to ``PIPEFY_MCP_HOST`` / ``PIPEFY_MCP_PORT``
    and matter only for the HTTP transport; stdio ignores them.

    ``resource_server`` is the ``(verifier, auth)`` pair from
    :func:`pipefy_mcp.auth.build_resource_server_auth`. When present, FastMCP
    validates the inbound bearer per request and serves the resource-server
    metadata; when ``None`` (stdio, or an HTTP local profile) the app has no
    inbound auth.
    """
    resolved = (
        (settings.mcp.profile == "remote") if remote_mode is None else remote_mode
    )
    resolved_host, resolved_port = _resolve_bind(host, port)
    verifier, auth = resource_server or (None, None)
    runtime = McpRuntime(settings, _select_auth_source(settings, resource_server))
    app = FastMCP(
        "pipefy",
        instructions=PIPEFY_INSTRUCTIONS,
        lifespan=_make_lifespan(runtime),
        host=resolved_host,
        port=resolved_port,
        token_verifier=verifier,
        auth=auth,
    )
    _register_pipefy_tools(app, remote_mode=resolved)
    return app


def _assert_safe_http_bind(*, host: str) -> None:
    """Refuse to bind the HTTP transport to a non-loopback host.

    The HTTP transport is restricted to loopback for now. The resource-server
    profile now carries per-request on-behalf-of identity (each call runs as the
    validated caller, not a single startup identity), so that is no longer the
    blocker; the remaining one is DNS-rebinding protection, the configurable
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


def run_server(
    *,
    profile: str | None = None,
    transport: str | None = None,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Run the Pipefy MCP server. The single serve entry point for both transports.

    The launch flags are resolved once through :func:`resolve_mcp_settings` (argv
    beats ``PIPEFY_MCP_*``), which fills the profile-derived transport default and
    rejects an incompatible pair. ``transport == "stdio"`` speaks MCP over stdio;
    ``transport == "http"`` serves over Streamable HTTP on ``host``/``port``
    (defaulting to ``PIPEFY_MCP_HOST`` / ``PIPEFY_MCP_PORT``), restricted to a
    loopback bind until the hosted on-behalf-of profile lands (see
    :func:`_assert_safe_http_bind`).

    ``profile == "remote"`` selects the default-deny remote-safe tool surface and,
    when ``resource_server_url`` is configured, validates an inbound bearer per
    request. ``local`` registers every tool and runs as the one startup credential.

    The server is built here, at startup rather than at import. Building registers
    every tool and reads the profile, so building at import would make
    ``--version``/``--help`` pay the full cost and turn any registration error into
    an import failure.

    Both transports build the same app through :func:`build_pipefy_mcp_server`
    (same runtime-bound lifespan, same :func:`_register_pipefy_tools`) and differ
    only in the transport ``run`` and HTTP's bind concerns.
    """
    mcp = resolve_mcp_settings(
        profile=profile, transport=transport, host=host, port=port
    )
    remote_profile = mcp.profile == "remote"

    if mcp.transport == "stdio":
        logger.info("Starting Pipefy MCP server over stdio (profile=%s)", mcp.profile)
        build_pipefy_mcp_server(remote_mode=remote_profile).run()
        return

    # The resource server (inbound bearer validation) is only meaningful for the
    # remote profile; a local server over loopback HTTP trusts its peer and skips
    # it. The remote profile acts on behalf of the caller, so it needs a
    # per-request bearer to validate: a configured resource server is mandatory.
    # Without one the builder returns None and there would be no per-request
    # identity to act as, so fail fast rather than silently fall back to a single
    # startup credential.
    resource_server = None
    if remote_profile:
        oidc_client = settings.auth.to_oidc_client()
        resource_server = build_resource_server_auth(
            settings.rs,
            settings.jwt,
            default_issuer_url=oidc_client.issuer_url if oidc_client else None,
        )
        if resource_server is None:
            raise RuntimeError(
                "the 'remote' profile requires a resource server: set "
                "PIPEFY_MCP_RS_RESOURCE_SERVER_URL so the server validates a "
                "per-request bearer and acts on behalf of the caller."
            )
    logger.info(
        "Starting Pipefy MCP server over HTTP on %s:%d (profile=%s, resource_server=%s)",
        mcp.host,
        mcp.port,
        mcp.profile,
        "active" if resource_server is not None else "inactive",
    )
    _assert_safe_http_bind(host=mcp.host)

    app = build_pipefy_mcp_server(
        remote_mode=remote_profile,
        host=mcp.host,
        port=mcp.port,
        resource_server=resource_server,
    )
    app.run("streamable-http")
