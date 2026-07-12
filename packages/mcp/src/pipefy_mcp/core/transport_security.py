"""Derive the HTTP transport's DNS-rebinding allowlist from settings.

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
SDK's ``AuthSettings``). It lives in the composition tier because transport security
owns no concern folder of its own, and the mcp-SDK type is kept out of
``settings.py`` so the config boundary stays framework-free.

The public host is derived from ``resource_server_url`` (which the remote profile
already requires), so the standard fronted deployment needs no allowlist config;
``allowed_hosts`` / ``allowed_origins`` extend it. When nothing is configured the
function returns ``None``, leaving FastMCP's own loopback default in force.
"""

from __future__ import annotations

from urllib.parse import urlparse

from mcp.server.transport_security import TransportSecuritySettings

from pipefy_mcp.settings import Settings

# Loopback entries kept in every explicit allowlist so widening for a proxy does
# not lock out local tooling on the box (a proxy on the same host still reaches the
# server over loopback). Mirrors FastMCP's own loopback auto-enable set.
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def _host_forms(host: str) -> tuple[str, str]:
    """The two match forms for a Host entry: exact, and any-port (``host:*``).

    The SDK matches a Host header by exact string or a trailing ``:*`` port
    wildcard, and ``localhost:*`` does not match a portless ``localhost``, so both
    forms are listed to cover a Host sent with or without a port.
    """
    return host, f"{host}:*"


def _resource_hosts(resource_server_url: str | None) -> list[str]:
    """The public Host forms carried by ``resource_server_url``, if set."""
    if not resource_server_url:
        return []
    parsed = urlparse(resource_server_url)
    hosts: list[str] = []
    if parsed.hostname:
        hosts.append(parsed.hostname)
    # netloc carries host:port; include it when a port is present so a proxy that
    # forwards "host:port" as the Host still matches the exact form.
    if parsed.port and parsed.netloc not in hosts:
        hosts.append(parsed.netloc)
    return hosts


def build_transport_security(settings: Settings) -> TransportSecuritySettings | None:
    """Resolve the transport allowlist, or ``None`` to keep FastMCP's default.

    Returns ``None`` when there is nothing to add beyond loopback (no
    ``resource_server_url`` and no explicit ``allowed_hosts`` / ``allowed_origins``),
    so FastMCP applies its own loopback auto-enable and current behavior is
    preserved. Otherwise it enables DNS-rebinding protection over loopback plus the
    derived public host and any explicit entries.
    """
    public_hosts = _resource_hosts(settings.rs.resource_server_url)
    public_hosts += settings.mcp.allowed_hosts or []
    explicit_origins = settings.mcp.allowed_origins

    if not public_hosts and not explicit_origins:
        return None

    allowed_hosts: list[str] = []
    for host in (*_LOOPBACK_HOSTS, *public_hosts):
        for form in _host_forms(host):
            if form not in allowed_hosts:
                allowed_hosts.append(form)

    if explicit_origins:
        allowed_origins = list(explicit_origins)
    else:
        allowed_origins = []
        for host in allowed_hosts:
            for scheme in ("http", "https"):
                origin = f"{scheme}://{host}"
                if origin not in allowed_origins:
                    allowed_origins.append(origin)

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


__all__ = ["build_transport_security"]
