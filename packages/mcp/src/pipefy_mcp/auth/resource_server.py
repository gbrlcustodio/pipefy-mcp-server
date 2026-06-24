"""Inbound bearer validation for the OAuth 2.0 resource-server profile.

The HTTP transport acts as an OAuth resource server (RFC 6749 §1.1): it accepts
an ``Authorization: Bearer`` on every request and validates the access token
before any tool runs. :class:`JwtTokenVerifier` implements FastMCP's
``TokenVerifier`` protocol so the SDK's bearer middleware drives it; FastMCP
emits the ``401`` + ``WWW-Authenticate`` challenge and serves the RFC 9728
protected-resource metadata around it.

This is a thin adapter: the JWKS resolution and RS256 decoding live in
``pipefy_auth`` (:class:`~pipefy_auth.JwtValidator`, a transport-agnostic auth
primitive). This class maps the validated claims onto the SDK's ``AccessToken``
and turns a validation failure into the ``None`` the protocol reads as "reject".
The validated token then lands in the MCP auth context for the per-request
on-behalf-of work tracked separately.
"""

from __future__ import annotations

import asyncio
import logging

from mcp.server.auth.provider import AccessToken, TokenVerifier
from pipefy_auth import JwtValidator

logger = logging.getLogger(__name__)


class JwtTokenVerifier(TokenVerifier):
    """Adapt :class:`~pipefy_auth.JwtValidator` to FastMCP's ``TokenVerifier``."""

    def __init__(self, validator: JwtValidator) -> None:
        self._validator = validator

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return the validated token, or ``None`` to reject it (FastMCP -> 401).

        The validator is synchronous, so it runs off the event loop. A
        ``ValueError`` (the base of ``TokenValidationError``) is a rejection, not
        a raise: the SDK turns ``None`` into the ``401`` challenge.
        """
        try:
            claims = await asyncio.to_thread(self._validator.validate, token)
        except ValueError as exc:
            logger.warning("Inbound bearer rejected: %s", exc)
            return None

        return AccessToken(
            token=token,
            # OAuth/OIDC precedence: azp (authorized party) over client_id over
            # sub, so a token minted via exchange reports the acting client.
            client_id=(
                claims.get("azp") or claims.get("client_id") or claims.get("sub", "")
            ),
            scopes=(claims.get("scope") or "").split(),
            expires_at=claims.get("exp"),
            resource=self._validator.audience,
        )
