"""SSRF-related URL checks used when validating the OIDC issuer URL.

This is a deliberate inline copy of the equivalent function in
``pipefy_sdk.utils.url_ssrf`` — pipefy-auth is a leaf workspace package and
must not depend on pipefy-sdk. The duplication is small (one function), and
the two copies can be deduplicated later by extracting a shared utilities
package if one is needed for other reasons.
"""

from __future__ import annotations

import ipaddress
from typing import Final
from urllib.parse import urlparse

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


def _assert_hostname_is_not_internal(hostname: str, *, context: str) -> None:
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


def validate_https_service_endpoint_url(
    url: str,
    field_label: str,
    *,
    allow_insecure: bool = False,
) -> None:
    """Validate URLs used for the OIDC issuer / token / authorization endpoints.

    When ``allow_insecure`` is True (``PIPEFY_ALLOW_INSECURE_URLS``), only scheme
    and hostname are required so local development can use ``http`` and internal
    hosts.

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

    _assert_hostname_is_not_internal(parsed.hostname, context=field_label)


__all__ = ["validate_https_service_endpoint_url"]
