"""OIDC discovery: fetch ``.well-known/openid-configuration`` from an issuer URL."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from pipefy_cli.oauth._http import http_client

DISCOVERY_PATH = "/.well-known/openid-configuration"
_DEFAULT_TIMEOUT = 10.0


@dataclass(frozen=True)
class ProviderMetadata:
    """Subset of OIDC provider metadata the login flow needs."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str


def _normalize_issuer(issuer_url: str) -> str:
    return issuer_url.rstrip("/")


def discovery_url(issuer_url: str) -> str:
    """Return the well-known discovery URL for ``issuer_url``."""
    return f"{_normalize_issuer(issuer_url)}{DISCOVERY_PATH}"


def fetch_provider_metadata(
    issuer_url: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    client: httpx.Client | None = None,
) -> ProviderMetadata:
    """Fetch and parse the issuer's OIDC discovery document.

    Raises:
        ValueError: When the discovery document is unreachable, malformed, or
            missing required endpoints. Message is user-facing.
    """
    url = discovery_url(issuer_url)
    with http_client(client, timeout=timeout) as http:
        try:
            response = http.get(url)
        except httpx.HTTPError as exc:
            raise ValueError(
                f"Could not reach Pipefy auth server at {url}: {exc}"
            ) from exc

    if response.status_code != 200:
        raise ValueError(
            f"OIDC discovery failed ({response.status_code}) at {url}: "
            f"{response.text[:200]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError(
            f"OIDC discovery returned non-JSON body at {url}: {exc}"
        ) from exc

    required = ("issuer", "authorization_endpoint", "token_endpoint")
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise ValueError(
            f"OIDC discovery at {url} is missing required fields: {', '.join(missing)}"
        )

    return ProviderMetadata(
        issuer=str(data["issuer"]),
        authorization_endpoint=str(data["authorization_endpoint"]),
        token_endpoint=str(data["token_endpoint"]),
    )


__all__ = [
    "DISCOVERY_PATH",
    "ProviderMetadata",
    "discovery_url",
    "fetch_provider_metadata",
]
