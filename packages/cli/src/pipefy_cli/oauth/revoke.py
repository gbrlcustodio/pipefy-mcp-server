"""OIDC end-session revocation: invalidate the refresh token at the IdP."""

from __future__ import annotations

import httpx

from pipefy_cli.oauth import _http
from pipefy_cli.oauth.discovery import DiscoveryPolicy, fetch_provider_metadata

_TIMEOUT_S = 30.0


class RevocationError(RuntimeError):
    """A revocation POST failed (discovery, network, or non-2xx response)."""


class RevocationUnsupportedError(RevocationError):
    """The IdP's discovery doc doesn't advertise ``end_session_endpoint``.

    Distinct from a transport failure so the CLI can phrase the warning honestly
    ("provider doesn't support server-side logout" vs. "couldn't reach provider").
    """


def revoke_session(
    *,
    issuer: str,
    client_id: str,
    refresh_token: str,
    policy: DiscoveryPolicy = DiscoveryPolicy(),
    http_client: httpx.Client | None = None,
) -> None:
    """POST to the IdP's ``end_session_endpoint`` to revoke ``refresh_token``.

    Raises:
        RevocationUnsupportedError: When the discovery doc doesn't advertise an
            ``end_session_endpoint``.
        RevocationError: For any other revocation failure (discovery, network,
            non-2xx response). Caller decides whether to fail or warn.
    """
    with _http.http_client(http_client, timeout=_TIMEOUT_S) as http:
        try:
            metadata = fetch_provider_metadata(issuer, policy=policy, client=http)
        except ValueError as exc:
            raise RevocationError(f"OIDC discovery failed: {exc}") from exc
        if metadata.end_session_endpoint is None:
            raise RevocationUnsupportedError(
                "OIDC provider does not advertise an end_session_endpoint."
            )
        try:
            response = http.post(
                metadata.end_session_endpoint,
                data={"client_id": client_id, "refresh_token": refresh_token},
            )
        except httpx.HTTPError as exc:
            raise RevocationError(f"Revocation request failed: {exc}") from exc

    # Keycloak returns 204; RFC treats any 2xx as success. No body echo on
    # failure — we just sent ``refresh_token`` in the POST body, so a ``[:N]``
    # window would be a guaranteed leak channel under a hostile IdP (same
    # threat model as ``flow._format_token_error``).
    if response.status_code // 100 != 2:
        raise RevocationError(
            f"Revocation endpoint returned HTTP {response.status_code}"
        )


__all__ = ["RevocationError", "RevocationUnsupportedError", "revoke_session"]
