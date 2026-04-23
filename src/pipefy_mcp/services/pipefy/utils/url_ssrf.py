"""SSRF-related URL checks shared across download and HTTP clients."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Final

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


__all__ = ["assert_hostname_resolves_to_public_ips"]
