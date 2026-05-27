"""SSRF defenses on URLs destined for outbound HTTP.

Three layered gates against server-side request forgery:

* :data:`URL_SHAPE_PATTERN`: regex used in ``Field(..., pattern=...)`` on
  settings fields that carry an https URL. Rejects malformed inputs (no
  scheme, wrong scheme, whitespace) before any deeper check can run.
* :func:`validate_https_url`: synchronous gate used at settings
  construction (and on every webhook / internal-API URL accepted from user
  input). Rejects literal IPs in private/loopback/link-local ranges via
  :func:`assert_hostname_is_not_internal`.
* :func:`assert_hostname_resolves_to_public_ips`: asynchronous DNS gate
  used right before issuing a request, so a DNS-rebinding attacker cannot
  point a public name at an internal IP between validation and connection.

Import the module itself (``from pipefy_infra import security``) and call
through it (``security.validate_https_url(...)``); the ``security.``
prefix at every call site keeps the SSRF surface trivially greppable for
audits.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Final
from urllib.parse import urlparse

# URL-shape gate for ``Field(..., pattern=URL_SHAPE_PATTERN)`` on settings
# fields that carry an https URL. The deeper SSRF + scheme check
# (:func:`validate_https_url`) runs after settings construction. The
# scheme part is case-insensitive (RFC 3986 §3.1) so
# ``HTTPS://...`` from operator copy-paste passes the shape gate; httpx and
# gql normalize the scheme downstream.
URL_SHAPE_PATTERN = r"^(?i:https?)://\S+$"

_PRIVATE_NETWORKS: Final = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fd00::/8"),
    ipaddress.ip_network("fe80::/10"),
)


def assert_hostname_is_not_internal(hostname: str, *, context: str) -> None:
    """Reject localhost and literal IPs in private/link-local/reserved ranges.

    Domain names are not DNS-resolved here (use :func:`assert_hostname_resolves_to_public_ips`
    before fetching). This blocks obvious internal targets in the URL host slot.

    Raises:
        ValueError: When the host is disallowed.
    """
    host = (hostname or "").strip().lower()
    if not host:
        msg = f"{context}: URL must include a hostname."
        raise ValueError(msg)
    if host == "localhost":
        msg = f"{context}: localhost hostnames are not allowed."
        raise ValueError(msg)

    try:
        ip = ipaddress.ip_address(hostname.strip())
    except ValueError:
        return

    for net in _PRIVATE_NETWORKS:
        if ip in net:
            msg = (
                f"{context}: {hostname!r} is a private, loopback, or link-local address "
                "and is not allowed."
            )
            raise ValueError(msg)


def validate_https_url(
    url: str,
    field_label: str,
    *,
    allow_insecure: bool = False,
) -> None:
    """Validate a URL destined for outbound HTTP.

    Enforces HTTPS and rejects literal private / loopback / link-local IPs in
    the host slot. When ``allow_insecure`` is True
    (``PIPEFY_ALLOW_INSECURE_URLS``), only scheme and hostname are required so
    local development can use ``http`` and internal hosts.

    Raises:
        ValueError: When the URL is missing parts or violates policy.
    """
    stripped = url.strip()
    parsed = urlparse(stripped)
    if not parsed.scheme:
        msg = f"{field_label}: URL must include a scheme."
        raise ValueError(msg)
    if not parsed.hostname:
        msg = f"{field_label}: URL must include a hostname."
        raise ValueError(msg)

    if allow_insecure:
        if parsed.scheme.lower() not in ("http", "https"):
            msg = f"{field_label}: must use http or https."
            raise ValueError(msg)
        return

    if parsed.scheme.lower() != "https":
        msg = f"{field_label}: must use HTTPS (http is not allowed)."
        raise ValueError(msg)

    assert_hostname_is_not_internal(parsed.hostname, context=field_label)


async def assert_hostname_resolves_to_public_ips(hostname: str) -> None:
    """Resolve ``hostname`` and ensure no address is private or link-local.

    DNS resolution runs in a thread pool to avoid blocking the event loop.

    Raises:
        ValueError: When resolution fails or any resolved IP is blocked.
    """
    if not hostname:
        msg = "URL has no hostname."
        raise ValueError(msg)

    try:
        loop = asyncio.get_event_loop()
        addr_info = await loop.run_in_executor(
            None, socket.getaddrinfo, hostname, None, 0, socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        msg = f"Could not resolve hostname {hostname!r}: {exc}"
        raise ValueError(msg) from exc

    for _family, _type, _proto, _canonname, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        for net in _PRIVATE_NETWORKS:
            if ip in net:
                msg = (
                    f"Host {hostname!r} resolves to a private/internal address ({ip}). "
                    "Request blocked."
                )
                raise ValueError(msg)


__all__ = [
    "URL_SHAPE_PATTERN",
    "assert_hostname_is_not_internal",
    "assert_hostname_resolves_to_public_ips",
    "validate_https_url",
]
