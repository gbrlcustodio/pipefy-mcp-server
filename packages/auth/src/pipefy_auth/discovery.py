"""OIDC discovery: fetch ``.well-known/openid-configuration`` from an issuer URL."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from pipefy_infra import validate_https_service_endpoint_url

from pipefy_auth import _http

DISCOVERY_PATH = "/.well-known/openid-configuration"
_DEFAULT_TIMEOUT = 10.0


@dataclass(frozen=True)
class ProviderMetadata:
    """Subset of OIDC provider metadata the login flow needs.

    ``end_session_endpoint`` is optional per OIDC Discovery 1.0 — not every IdP
    advertises it. ``auth logout`` soft-fails when it's absent (warns + clears
    the local session only).
    """

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    end_session_endpoint: str | None = None


@dataclass(frozen=True)
class DiscoveryPolicy:
    """Knobs governing how ``fetch_provider_metadata`` validates its inputs.

    Bundled so future flags (cached metadata, custom timeouts) can grow here
    without re-threading kwargs through every caller.
    """

    allow_insecure_urls: bool = False


def _normalize_issuer(issuer_url: str) -> str:
    return issuer_url.rstrip("/")


def discovery_url(issuer_url: str) -> str:
    """Return the well-known discovery URL for ``issuer_url``."""
    return f"{_normalize_issuer(issuer_url)}{DISCOVERY_PATH}"


def fetch_provider_metadata(
    issuer_url: str,
    *,
    policy: DiscoveryPolicy = DiscoveryPolicy(),
    timeout: float = _DEFAULT_TIMEOUT,
    client: httpx.Client | None = None,
) -> ProviderMetadata:
    """Fetch and parse the issuer's OIDC discovery document.

    Validates that ``metadata.issuer`` matches ``issuer_url`` (per OIDC
    Discovery 1.0 §4.3) and that the returned ``authorization_endpoint`` and
    ``token_endpoint`` aren't pointing at internal hosts or non-HTTPS URLs —
    a tampered or misconfigured discovery doc must not be allowed to redirect
    the browser dance or token exchange to an attacker-controlled target.

    Raises:
        ValueError: When the discovery document is unreachable, malformed,
            issuer-mismatched, or returns endpoint URLs that don't pass the
            shared SSRF check. Message is user-facing.
    """
    url = discovery_url(issuer_url)
    with _http.http_client(client, timeout=timeout) as http:
        try:
            response = http.get(url)
        except httpx.HTTPError as exc:
            raise ValueError(
                f"Could not reach Pipefy auth server at {url}: {exc}"
            ) from exc

    if response.status_code != 200:
        # Status-only; never echo the raw body. Discovery isn't OAuth so there's
        # no RFC 6749 ``error`` field to surface, and a `[:N]` window of the
        # body is the same echo-channel class scrubbed in ``_format_token_error``.
        raise ValueError(f"OIDC discovery failed ({response.status_code}) at {url}")

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

    # OIDC Discovery 1.0 §4.3 — the ``issuer`` claim must match the URL the
    # document was fetched from. Trailing slashes don't carry meaning here.
    claimed_issuer = str(data["issuer"])
    if _normalize_issuer(claimed_issuer) != _normalize_issuer(issuer_url):
        raise ValueError(
            f"OIDC discovery issuer mismatch: requested {issuer_url!r}, "
            f"document claims {claimed_issuer!r}"
        )

    authorization_endpoint = str(data["authorization_endpoint"])
    token_endpoint = str(data["token_endpoint"])
    raw_end_session = data.get("end_session_endpoint")
    end_session_endpoint = str(raw_end_session) if raw_end_session else None

    endpoints: list[tuple[str, str]] = [
        ("authorization_endpoint", authorization_endpoint),
        ("token_endpoint", token_endpoint),
    ]
    if end_session_endpoint is not None:
        endpoints.append(("end_session_endpoint", end_session_endpoint))
    for field, value in endpoints:
        try:
            validate_https_service_endpoint_url(
                value, field, allow_insecure=policy.allow_insecure_urls
            )
        except ValueError as exc:
            raise ValueError(f"OIDC discovery returned invalid {field}: {exc}") from exc

    return ProviderMetadata(
        issuer=claimed_issuer,
        authorization_endpoint=authorization_endpoint,
        token_endpoint=token_endpoint,
        end_session_endpoint=end_session_endpoint,
    )


__all__ = [
    "DISCOVERY_PATH",
    "DiscoveryPolicy",
    "ProviderMetadata",
    "discovery_url",
    "fetch_provider_metadata",
]
