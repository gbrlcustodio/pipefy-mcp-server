"""OIDC client identity shared by every consumer of the stored user session.

``client_id`` is the public OAuth client registered with Pipefy's IdP — its
literal value is ``"pipefy-cli"`` because that was the first consumer, but the
name does **not** bind the identity to the CLI. The same client_id is used by
the MCP server (and any future consumer) because the refresh token a user
obtains via ``pipefy auth login`` can only be redeemed by the client_id that
issued it. Renaming the client_id would require re-registering at the IdP and
invalidating every existing session — out of scope for this package.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_AUTH_CLIENT_ID = "pipefy-cli"


@dataclass(frozen=True)
class OidcClient:
    """OIDC client identity: issuer URL + the public client id registered there.

    The two fields are a single configurable unit; presence of an :class:`OidcClient`
    is what gates the stored-session tier of the credential precedence chain.
    """

    issuer_url: str
    client_id: str


__all__ = [
    "DEFAULT_AUTH_CLIENT_ID",
    "OidcClient",
]
