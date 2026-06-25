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
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.server.auth.provider import AccessToken, TokenVerifier
from pipefy_auth import JwtValidator

logger = logging.getLogger(__name__)


def _parse_scopes(scope: Any) -> list[str]:
    """Normalize the ``scope`` claim to a list of strings.

    RFC 9068 specifies a space-delimited string, but some IdPs emit a JSON
    array. Accept both and treat anything else as no scopes, so a non-string
    ``scope`` can't raise out of the claims mapping.
    """
    if isinstance(scope, str):
        return scope.split()
    if isinstance(scope, list):
        return [str(item) for item in scope]
    return []


class JwtTokenVerifier(TokenVerifier):
    """Adapt :class:`~pipefy_auth.JwtValidator` to FastMCP's ``TokenVerifier``."""

    def __init__(self, validator: JwtValidator, *, resource: str | None = None) -> None:
        self._validator = validator
        # The RFC 8707 resource this token targets, stamped onto every AccessToken.
        # Injected by the wiring layer that owns the resource-server identity,
        # rather than read back out of the validator's config.
        self._resource = resource

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return the validated token, or ``None`` to reject it (FastMCP -> 401).

        The validator is synchronous, so it runs off the event loop. Both a
        failed signature/claim check (``ValueError``, the base of
        ``TokenValidationError``) and an unmappable claim set are rejections, not
        raises: the SDK turns ``None`` into the ``401`` challenge, so a malformed
        token must never escape as a 500.
        """
        try:
            claims = await asyncio.to_thread(self._validator.validate, token)
        except ValueError as exc:
            logger.warning("Inbound bearer rejected: %s", exc)
            return None

        try:
            return self._to_access_token(token, claims)
        except (ValueError, TypeError) as exc:
            # A validly-signed token can still carry claims we can't map onto an
            # AccessToken (e.g. an exp outside int range). Reject rather than let
            # the mapping error escape verify_token as a 500.
            logger.warning("Inbound bearer rejected (unmappable claims): %s", exc)
            return None

    def _to_access_token(self, token: str, claims: dict[str, Any]) -> AccessToken:
        exp = claims.get("exp")
        return AccessToken(
            token=token,
            # OAuth/OIDC precedence: azp (authorized party) over client_id over
            # sub, so a token minted via exchange reports the acting client.
            client_id=(
                claims.get("azp") or claims.get("client_id") or claims.get("sub", "")
            ),
            scopes=_parse_scopes(claims.get("scope")),
            # exp is an RFC 7519 NumericDate (may be fractional); AccessToken
            # wants an int. The validator requires exp, so it is present here.
            expires_at=int(exp) if exp is not None else None,
            resource=self._resource,
        )
