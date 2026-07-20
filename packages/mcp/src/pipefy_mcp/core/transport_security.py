"""Derive the HTTP transport's DNS-rebinding allowlist.

FastMCP auto-enables a loopback-only Host/Origin allowlist whenever it is built
with a loopback ``host`` and no explicit ``transport_security``. The builder always
passes ``host=settings.mcp.host`` (default ``127.0.0.1``), so behind a proxy that
forwards the public Host the transport answers ``421 Misdirected Request`` before
any handler runs. This module turns the resolved settings into the
``TransportSecuritySettings`` that widens the allowlist to the public host while
keeping DNS-rebinding protection on.

This is configuration resolution, not an MCP extension: it produces a static
config value the SDK reads, mirroring
:func:`pipefy_mcp.auth.resource_server.build_resource_server_auth` (settings to the
SDK's ``AuthSettings``). The mcp-SDK type is kept out of ``settings.py`` so the
config boundary stays framework-free.

The public host comes from the :class:`pipefy_mcp.auth.ResourceServer` the runtime
parses once and feeds in (which the remote profile already requires), so the standard
fronted deployment needs no allowlist config; ``allowed_hosts`` / ``allowed_origins``
extend it. When neither a resource nor an explicit allowlist is given the function
returns ``None``, leaving FastMCP's own loopback default in force.
"""

from __future__ import annotations

from mcp.server.transport_security import TransportSecuritySettings

from pipefy_mcp.auth import ResourceServer
from pipefy_mcp.settings import McpSettings

# Loopback entries kept in every explicit allowlist so widening for a proxy does
# not lock out local tooling on the box (a proxy on the same host still reaches the
# server over loopback). Mirrors FastMCP's own loopback auto-enable set.
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def build_transport_security(
    mcp: McpSettings, resource: ResourceServer | None
) -> TransportSecuritySettings | None:
    """Resolve the transport allowlist, or ``None`` to keep FastMCP's default.

    Returns ``None`` only when there is nothing to configure: no ``resource``, no
    ``allowed_hosts``, and an unset (``None``) ``allowed_origins``, so FastMCP applies
    its own loopback auto-enable and current behavior is preserved. Otherwise it
    enables DNS-rebinding protection over loopback plus the resource's public host and
    any explicit entries. An explicit ``allowed_origins`` (including an empty list,
    which rejects any request that sends an Origin) is honored verbatim; only an unset
    list falls back to the origins derived from the allowed hosts.
    """
    public_hosts = list(resource.host_authorities) if resource else []
    public_hosts += mcp.allowed_hosts or []
    explicit_origins = mcp.allowed_origins

    # An explicit origin allowlist (including an empty one) is an override worth
    # honoring, so it keeps protection on even with no host to add: ``allowed_origins=[]``
    # is the strictest posture, rejecting any request that sends an Origin. Only an
    # unset origin list plus no host leaves nothing to configure.
    if not public_hosts and explicit_origins is None:
        return None

    # Each host contributes an exact form and a ``host:*`` any-port form: the SDK
    # matches a Host header by exact string or trailing ``:*`` wildcard, and
    # ``localhost:*`` does not match a portless ``localhost``, so both cover a Host
    # sent with or without a port. ``dict.fromkeys`` dedupes while keeping order.
    allowed_hosts = list(
        dict.fromkeys(
            form
            for host in (*_LOOPBACK_HOSTS, *public_hosts)
            for form in (host, f"{host}:*")
        )
    )

    if explicit_origins is not None:
        allowed_origins = list(explicit_origins)
    else:
        # allowed_hosts is already deduped and (host, scheme) is injective, so no
        # duplicate origin can arise; derive directly with no dedup pass.
        allowed_origins = [
            f"{scheme}://{host}"
            for host in allowed_hosts
            for scheme in ("http", "https")
        ]

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


__all__ = ["build_transport_security"]
