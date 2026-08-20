"""Client-identifying headers attached to outbound Pipefy requests.

Pure builders: given the product, surface, deployment, and package version, they
return the header dict the transports attach. Lives in ``pipefy_infra`` so the SDK
(API requests) and the auth package (OAuth requests) share one ``User-Agent``
format.

The client is described by two orthogonal axes: the **surface** says which entry
point ran (``mcp``, ``cli``, ``sdk``), and the **deployment** says where that entry
point runs (``local``, ``hosted``). Both are stamped programmatically at a
composition root and are never read from env or TOML, so a caller cannot forge
either.
"""

from __future__ import annotations

from typing import Literal

ClientSurface = Literal["mcp", "cli", "sdk"]
"""The calling surface: ``mcp`` (server), ``cli``, or ``sdk`` (direct SDK use)."""

ClientDeployment = Literal["local", "hosted"]
"""Where the surface runs: ``local`` (the user's own machine) or ``hosted``.

Orthogonal to :data:`ClientSurface`: the same ``mcp`` surface is ``local`` as a
stdio server on a user's machine and ``hosted`` as a remote-profile deployment.
Both sides are labelled explicitly so a bare ``(mcp)`` reads as "client older than
this axis", never as ``local``.
"""


def telemetry_user_agent(
    *,
    version: str,
    surface: ClientSurface | None = None,
    deployment: ClientDeployment | None = None,
    product: str = "pipefy-sdk",
) -> str:
    """``User-Agent`` value: ``<product>/<version> (<surface>; <deployment>)``.

    The parenthetical grows with what the caller knows: no surface yields a bare
    ``<product>/<version>``, a surface alone yields ``(<surface>)``, and a surface
    plus a deployment yields ``(<surface>; <deployment>)``.

    The API path passes a surface, and the surfaces that can run in more than one
    place also pass a deployment; the OAuth path passes neither (they never reach
    the auth layer) and overrides ``product`` to ``pipefy-auth``.
    """
    if surface is None:
        return f"{product}/{version}"
    if deployment is None:
        return f"{product}/{version} ({surface})"
    return f"{product}/{version} ({surface}; {deployment})"


def telemetry_headers(
    *,
    surface: ClientSurface,
    version: str,
    deployment: ClientDeployment | None = None,
) -> dict[str, str]:
    """Headers identifying the client on every outbound Pipefy API request.

    ``User-Agent`` carries client, version, surface, and deployment in one field;
    ``X-Client-Name`` / ``X-Client-Version`` / ``X-Client-Deployment`` repeat those
    axes as parsed fields so the server can group traffic without matching on the
    ``User-Agent`` string.

    ``X-Client-Deployment`` is sent only when the caller supplies a ``deployment``,
    so a surface that runs in exactly one place (the CLI) keeps the three-header
    shape it has always sent.
    """
    headers = {
        "User-Agent": telemetry_user_agent(
            surface=surface, version=version, deployment=deployment
        ),
        "X-Client-Name": surface,
        "X-Client-Version": version,
    }
    if deployment is not None:
        headers["X-Client-Deployment"] = deployment
    return headers


def auth_telemetry_headers(*, version: str) -> dict[str, str]:
    """Headers identifying the OAuth client on outbound requests to the IdP.

    ``X-Client-Name`` is ``auth`` (the component making the request, not an API
    surface) and the ``User-Agent`` product is ``pipefy-auth``, since the auth
    package owns these requests and neither the surface nor the deployment reaches
    this layer.
    """
    return {
        "User-Agent": telemetry_user_agent(version=version, product="pipefy-auth"),
        "X-Client-Name": "auth",
        "X-Client-Version": version,
    }


__all__ = [
    "ClientDeployment",
    "ClientSurface",
    "auth_telemetry_headers",
    "telemetry_headers",
    "telemetry_user_agent",
]
