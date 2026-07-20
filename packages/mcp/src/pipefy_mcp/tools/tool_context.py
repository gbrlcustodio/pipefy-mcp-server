"""Resolve request-scoped resources from the MCP lifespan context."""

from __future__ import annotations

from mcp.server.fastmcp import Context
from pipefy_sdk import PipefyClient

from pipefy_mcp.core.ipaas_gateway import IpaasGateway
from pipefy_mcp.core.runtime import McpRuntime


def get_ipaas_gateway(ctx: Context) -> IpaasGateway | None:
    """Return the deployment's iPaaS gateway, or None when unconfigured.

    A per-deployment resource built once at startup (identical for every
    caller — the gateway is stateless and holds no identity; the caller's
    identity enters the chain through the pipe-scoped token the tool mints
    via its own session). Tools translate None into a clear "not configured"
    error payload rather than failing registration.
    """
    runtime: McpRuntime = ctx.request_context.lifespan_context
    return runtime.ipaas_gateway


def is_remote_profile(ctx: Context) -> bool:
    """Whether this server is running the hosted ``remote`` profile.

    The call-time half of the "exposure vs input restriction" pattern
    (see the remote-profile section of the package CLAUDE.md): a tool that is
    exposed remotely but has inputs that only make sense against a
    single-user local process (e.g. ``$env`` credential references, which
    read the server's own environment) rejects those inputs per call. Read
    off the runtime, not the module-global settings singleton, so embedders
    and tests that build a runtime from explicit settings get the same
    answer the serving profile was resolved from.
    """
    runtime: McpRuntime = ctx.request_context.lifespan_context
    return runtime.settings.mcp.profile == "remote"


def get_pipefy_client(ctx: Context) -> PipefyClient:
    """Return a Pipefy client session bound to the in-flight request's identity.

    The server builds the app-scoped :class:`McpRuntime` at startup and its
    lifespan yields it as the request ``lifespan_context``. The runtime owns the
    shared engine and opens a cheap session here, per call, bound to the caller's
    identity (see :meth:`McpRuntime.session_for_request`). Resolving per call, not
    at registration, is what keeps identity request-scoped: under the hosted
    profile the session carries this request's validated bearer, read off the
    message's own ``request_context.request`` and passed in, so concurrent callers
    each act as themselves without re-registering the tool table.
    """
    request_context = ctx.request_context
    runtime: McpRuntime = request_context.lifespan_context
    return runtime.session_for_request(request_context.request)
