"""Inbound bearer validation for the OAuth 2.0 resource-server profile.

The HTTP transport acts as an OAuth resource server (RFC 6749 §1.1): it accepts
an ``Authorization: Bearer`` on every request and validates the access token
before any tool runs. :class:`JwtTokenVerifier` implements FastMCP's
``TokenVerifier`` protocol so the SDK's bearer middleware drives it; FastMCP
emits the ``401`` + ``WWW-Authenticate`` challenge and serves the RFC 9728
protected-resource metadata around it.

:class:`JwtTokenVerifier` is a thin adapter: the JWKS resolution and RS256
decoding live in ``pipefy_auth`` (:class:`~pipefy_auth.JwtValidator`, a
transport-agnostic auth primitive). This class maps the validated claims onto
the SDK's ``AccessToken`` and turns a validation failure into the ``None`` the
protocol reads as "reject".

:func:`build_resource_server_auth` is the composition root for this profile: it
resolves the inbound issuer, constructs the verifier over a ``JwtValidator``,
and pairs it with FastMCP's ``AuthSettings`` for the server to wire in.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings as FastMcpAuthSettings
from pipefy_auth import (
    AudiencePolicy,
    JwtValidationSettings,
    JwtValidator,
    RequireAudience,
    SkipAudience,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResourceServer:
    """A validated resource-server URL paired with its parsed Host authorities.

    Built by :meth:`from_url` at composition, so holding one is proof its
    ``host_forms`` are resolved before any read. ``url`` is the verbatim RFC 9728
    resource identifier (kept exact, as clients compare against it); ``host_forms``
    are the Host-header wire forms it presents, which the transport allowlist widens.
    """

    url: str
    host_forms: tuple[str, ...]

    @classmethod
    def from_url(cls, url: str) -> ResourceServer:
        """Parse an already-validated URL into its wire-form Host authorities.

        An IPv6 literal is bracketed, as the wire Host carries it (``urlparse``
        reports it unbracketed); a URL that names a port also contributes the
        ``host:port`` form.
        """
        parsed = urlparse(url)
        hostname = parsed.hostname
        forms: list[str] = []
        if hostname:
            host = f"[{hostname}]" if ":" in hostname else hostname
            forms.append(host)
            if parsed.port:
                forms.append(f"{host}:{parsed.port}")
        return cls(url=url, host_forms=tuple(forms))


class PipefyAccessToken(AccessToken):
    """AccessToken with the JWT ``sub`` claim preserved for request logging."""

    sub: str | None = None


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
        # OAuth/OIDC precedence: azp (authorized party) over client_id over sub,
        # so a token minted via exchange reports the acting client. A token
        # carrying none of the three has no usable identity; reject it rather
        # than stamp an anonymous "" client_id that AccessToken would accept.
        client_id = claims.get("azp") or claims.get("client_id") or claims.get("sub")
        if not client_id:
            raise ValueError("token carries no azp, client_id, or sub claim")

        # The validator requires exp, so a missing one cannot reach here through
        # the real path; reject defensively rather than emit a never-expiring
        # token (the bearer middleware reads a falsy expires_at as "no expiry")
        # if that invariant ever changes.
        exp = claims.get("exp")
        if exp is None:
            raise ValueError("token has no exp claim")

        # sub feeds request logging only; a malformed (non-string) sub must
        # degrade to None, not reject a token the verifier accepted before the
        # field existed.
        sub_claim = claims.get("sub")

        return PipefyAccessToken(
            token=token,
            client_id=client_id,
            scopes=_parse_scopes(claims.get("scope")),
            # exp is an RFC 7519 NumericDate (may be fractional); AccessToken
            # wants an int.
            expires_at=int(exp),
            resource=self._resource,
            sub=sub_claim if isinstance(sub_claim, str) else None,
        )


# The (verifier, auth) pair the server threads into FastMCP for the
# resource-server profile: the inbound bearer verifier and FastMCP's matching
# AuthSettings (RFC 9728 metadata + the 401 challenge).
ResourceServerAuth = tuple[JwtTokenVerifier, FastMcpAuthSettings]


def build_resource_server_auth(
    resource: ResourceServer,
    jwt_validation: JwtValidationSettings,
    *,
    default_issuer_url: str | None,
    required_scopes: list[str] | None = None,
) -> ResourceServerAuth:
    """Build the inbound bearer verifier and FastMCP auth config for ``resource``.

    Called only when the resource-server profile is active: the composition root
    parses the configured ``resource_server_url`` into ``resource`` and gates on its
    presence, so this receives an already-parsed identity and never a ``None``.

    The inbound issuer is ``jwt_validation.issuer_url`` if set, else
    ``default_issuer_url`` (see :class:`JwtValidationSettings` for why the login
    issuer is the fallback). With ``resource`` set but no issuer resolvable (the
    stored-session login is disabled and no override is given), validation is
    impossible, so this raises rather than serve an open endpoint.
    """
    issuer_url = jwt_validation.resolve_issuer_url(default_issuer_url)
    if issuer_url is None:
        raise RuntimeError(
            "The resource-server profile is active "
            "(PIPEFY_MCP_RS_RESOURCE_SERVER_URL is set) but no inbound issuer is "
            "resolvable: set PIPEFY_JWT_ISSUER_URL, or leave the stored-session "
            "login enabled so its issuer can be reused."
        )
    # Fold the loose audience pair into the AudiencePolicy sum type. A
    # verify-without-audience is already rejected at JwtValidationSettings
    # construction, so `is not None` only narrows the Optional for the type
    # checker here; it is never the deciding branch.
    if jwt_validation.verify_audience and jwt_validation.audience is not None:
        audience_policy: AudiencePolicy = RequireAudience(jwt_validation.audience)
    else:
        audience_policy = SkipAudience()
    verifier = JwtTokenVerifier(
        JwtValidator(
            issuer_url=issuer_url,
            audience_policy=audience_policy,
            allow_insecure_urls=jwt_validation.allow_insecure_urls,
            jwks_uri=jwt_validation.jwks_uri,
        ),
        resource=resource.url,
    )
    auth = FastMcpAuthSettings(
        issuer_url=issuer_url,
        resource_server_url=resource.url,
        required_scopes=required_scopes,
    )
    return verifier, auth
