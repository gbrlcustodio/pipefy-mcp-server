"""OIDC client identity shared by every consumer of the stored user session."""

from __future__ import annotations

from dataclasses import dataclass

# Refresh tokens are bound to the client_id that obtained them, so this value
# is fixed across consumers (CLI, MCP, …) and not user-configurable.
DEFAULT_AUTH_CLIENT_ID = "pipefy-cli"


@dataclass(frozen=True)
class OidcClient:
    """OIDC client identity: issuer URL + the public client id registered there.

    Presence of an :class:`OidcClient` is what gates the stored-session method
    of the credential precedence chain.
    """

    issuer_url: str
    client_id: str


__all__ = [
    "DEFAULT_AUTH_CLIENT_ID",
    "OidcClient",
]
