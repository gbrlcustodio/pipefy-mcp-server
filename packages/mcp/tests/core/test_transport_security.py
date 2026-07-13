"""Tests for ``build_transport_security`` (the DNS-rebinding allowlist resolver)."""

import pytest

from pipefy_mcp.core.transport_security import build_transport_security
from pipefy_mcp.settings import McpSettings, ResourceServerSettings, Settings

_LOOPBACK_FORMS = {
    "127.0.0.1",
    "127.0.0.1:*",
    "localhost",
    "localhost:*",
    "[::1]",
    "[::1]:*",
}


def _settings(*, resource_server_url=None, allowed_hosts=None, allowed_origins=None):
    return Settings(
        mcp=McpSettings(allowed_hosts=allowed_hosts, allowed_origins=allowed_origins),
        rs=ResourceServerSettings(resource_server_url=resource_server_url),
    )


@pytest.mark.unit
def test_unset_returns_none_to_keep_fastmcp_default():
    """No resource URL and no explicit allowlist -> FastMCP's own default stands."""
    assert build_transport_security(_settings()) is None


@pytest.mark.unit
def test_resource_server_url_host_is_derived_and_protection_enabled():
    """The public host is added (bare and any-port) with loopback retained."""
    security = build_transport_security(
        _settings(resource_server_url="https://mcp.pipefy.com/mcp")
    )
    assert security is not None
    assert security.enable_dns_rebinding_protection is True
    assert "mcp.pipefy.com" in security.allowed_hosts
    assert "mcp.pipefy.com:*" in security.allowed_hosts
    assert _LOOPBACK_FORMS.issubset(set(security.allowed_hosts))


@pytest.mark.unit
def test_resource_server_url_with_explicit_port_keeps_host_and_hostport():
    """A URL carrying a port contributes both the bare host and host:port."""
    security = build_transport_security(
        _settings(resource_server_url="https://mcp.pipefy.com:8443/mcp")
    )
    assert security is not None
    assert "mcp.pipefy.com" in security.allowed_hosts
    assert "mcp.pipefy.com:8443" in security.allowed_hosts


@pytest.mark.unit
def test_ipv6_literal_resource_url_is_bracketed_to_match_the_wire_host():
    """An IPv6-literal host is bracketed, as the Host header carries it.

    urlparse reports the hostname unbracketed ('2606:4700:4700::1111'), but a
    client sends the bracketed form; without re-bracketing every request 421s.
    """
    security = build_transport_security(
        _settings(resource_server_url="https://[2606:4700:4700::1111]/mcp")
    )
    assert security is not None
    assert "[2606:4700:4700::1111]" in security.allowed_hosts
    assert "[2606:4700:4700::1111]:*" in security.allowed_hosts


@pytest.mark.unit
def test_ipv6_literal_with_port_keeps_bracketed_host_and_hostport():
    """A ported IPv6 URL contributes both the bracketed host and host:port."""
    security = build_transport_security(
        _settings(resource_server_url="https://[2606:4700:4700::1111]:8443/mcp")
    )
    assert security is not None
    assert "[2606:4700:4700::1111]" in security.allowed_hosts
    assert "[2606:4700:4700::1111]:8443" in security.allowed_hosts


@pytest.mark.unit
def test_explicit_allowed_hosts_extend_the_derived_set():
    """PIPEFY_MCP_ALLOWED_HOSTS adds to loopback and the resource host."""
    security = build_transport_security(
        _settings(
            resource_server_url="https://mcp.pipefy.com/mcp",
            allowed_hosts=["proxy.internal"],
        )
    )
    assert security is not None
    assert "mcp.pipefy.com" in security.allowed_hosts
    assert "proxy.internal" in security.allowed_hosts
    assert "proxy.internal:*" in security.allowed_hosts


@pytest.mark.unit
def test_explicit_allowed_hosts_alone_enable_protection():
    """An override with no resource URL still produces an enabled allowlist."""
    security = build_transport_security(_settings(allowed_hosts=["proxy.internal"]))
    assert security is not None
    assert security.enable_dns_rebinding_protection is True
    assert "proxy.internal" in security.allowed_hosts


@pytest.mark.unit
def test_derived_origins_cover_each_host_in_both_schemes():
    """Without an override, origins are http+https for every allowed host."""
    security = build_transport_security(
        _settings(resource_server_url="https://mcp.pipefy.com/mcp")
    )
    assert security is not None
    assert "http://mcp.pipefy.com" in security.allowed_origins
    assert "https://mcp.pipefy.com" in security.allowed_origins
    assert "http://localhost:*" in security.allowed_origins


@pytest.mark.unit
def test_explicit_allowed_origins_replace_the_derived_origins():
    """An explicit origin allowlist is used verbatim, not merged with derived."""
    security = build_transport_security(
        _settings(
            resource_server_url="https://mcp.pipefy.com/mcp",
            allowed_origins=["https://mcp.pipefy.com"],
        )
    )
    assert security is not None
    assert security.allowed_origins == ["https://mcp.pipefy.com"]
