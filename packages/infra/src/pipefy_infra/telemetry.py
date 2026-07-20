"""Client-identifying headers attached to outbound Pipefy requests.

Pure builders: given the product, surface, and package version, they return the
header dict the transports attach. Lives in ``pipefy_infra`` so the SDK (API
requests) and the auth package (OAuth requests) share one ``User-Agent`` format.
"""

from __future__ import annotations

from typing import Literal

ClientSurface = Literal["mcp", "cli", "sdk"]
"""The calling surface: ``mcp`` (server), ``cli``, or ``sdk`` (direct SDK use)."""


def telemetry_user_agent(
    *, version: str, surface: ClientSurface | None = None, product: str = "pipefy-sdk"
) -> str:
    """``User-Agent`` value: ``<product>/<version>``, plus ``(<surface>)`` when given.

    The API path passes a surface; the OAuth path omits it (it never reaches the
    auth layer) and overrides ``product`` to ``pipefy-auth``.
    """
    if surface is None:
        return f"{product}/{version}"
    return f"{product}/{version} ({surface})"


def telemetry_headers(*, surface: ClientSurface, version: str) -> dict[str, str]:
    """Headers identifying the client on every outbound Pipefy API request.

    ``User-Agent`` carries client, version, and surface in one field;
    ``X-Client-Name`` / ``X-Client-Version`` repeat the surface and version as
    parsed fields so the server can group traffic without matching on the
    ``User-Agent`` string.
    """
    return {
        "User-Agent": telemetry_user_agent(surface=surface, version=version),
        "X-Client-Name": surface,
        "X-Client-Version": version,
    }


def auth_telemetry_headers(*, version: str) -> dict[str, str]:
    """Headers identifying the OAuth client on outbound requests to the IdP.

    ``X-Client-Name`` is ``auth`` (the component making the request, not an API
    surface) and the ``User-Agent`` product is ``pipefy-auth``, since the auth
    package owns these requests and the surface does not reach this layer.
    """
    return {
        "User-Agent": telemetry_user_agent(version=version, product="pipefy-auth"),
        "X-Client-Name": "auth",
        "X-Client-Version": version,
    }


__all__ = [
    "ClientSurface",
    "auth_telemetry_headers",
    "telemetry_headers",
    "telemetry_user_agent",
]
