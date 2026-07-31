"""Inbound bearer validation for the OAuth 2.0 resource-server profile.

The HTTP transport acts as an OAuth resource server (RFC 6749 §1.1): it accepts
an ``Authorization: Bearer`` on every request and validates the access token
before any tool runs. :class:`JwtTokenVerifier` implements the SDK's
``TokenVerifier`` protocol so the SDK's bearer middleware drives it; the SDK
emits the ``401`` + ``WWW-Authenticate`` challenge and serves the RFC 9728
protected-resource metadata around it.

:class:`JwtTokenVerifier` is a thin adapter: the JWKS resolution and RS256
decoding live in ``pipefy_auth`` (:class:`~pipefy_auth.JwtValidator`, a
transport-agnostic auth primitive). This class maps the validated claims onto
the SDK's ``AccessToken`` and turns a validation failure into the ``None`` the
protocol reads as "reject".

The mapping populates ``subject`` and ``claims["iss"]`` as well as ``client_id``,
because those three are what the SDK's ``principal_components`` compares to decide
whether a request may use an existing Streamable HTTP session. See
:meth:`JwtTokenVerifier._to_access_token`.

:func:`build_resource_server_auth` constructs the verifier over a ``JwtValidator``
and pairs it with the SDK's ``AuthSettings`` for the server to wire in. It takes an
already-resolved issuer: the composition root
(:meth:`pipefy_mcp.core.runtime.McpRuntime.for_profile`) resolves the inbound issuer
and gates on it, so this builder only wires the resolved values in.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings as SdkAuthSettings
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
    ``host_authorities`` are resolved before any read. ``url`` is the verbatim RFC 9728
    resource identifier (kept exact, as clients compare against it); ``host_authorities``
    are the ``host[:port]`` values it presents in the ``Host`` header, which the
    transport allowlist widens.
    """

    url: str
    host_authorities: tuple[str, ...]

    @classmethod
    def from_url(cls, url: str) -> ResourceServer:
        """Parse an already-validated URL into its ``Host`` header authorities.

        An IPv6 literal is bracketed, as the wire Host carries it (``urlparse``
        reports it unbracketed); a URL that names a port also contributes the
        ``host:port`` authority.
        """
        parsed = urlparse(url)
        hostname = parsed.hostname
        authorities: list[str] = []
        if hostname:
            host = f"[{hostname}]" if ":" in hostname else hostname
            authorities.append(host)
            if parsed.port:
                authorities.append(f"{host}:{parsed.port}")
        return cls(url=url, host_authorities=tuple(authorities))


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
    """Adapt :class:`~pipefy_auth.JwtValidator` to the SDK's ``TokenVerifier``."""

    def __init__(self, validator: JwtValidator, *, resource: str | None = None) -> None:
        self._validator = validator
        # The RFC 8707 resource this token targets, stamped onto every AccessToken.
        # Injected by the wiring layer that owns the resource-server identity,
        # rather than read back out of the validator's config.
        self._resource = resource

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return the validated token, or ``None`` to reject it (the SDK -> 401).

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

        # `subject` and `claims["iss"]` are the two components the SDK's
        # `principal_components` reads on top of `client_id` to identify a
        # token's principal, and session ownership compares that whole triple:
        # a request whose triple differs from the session creator's gets a 404.
        # Supplying only `client_id` would collapse the comparison onto `azp`,
        # which for the hosted server is the one public OAuth client every end
        # user authorizes through (`--client-id pipefy-mcp`), so two users of
        # that client would share one authorization context. `subject`
        # namespaced by `iss` is what makes the check per-user.
        #
        # A malformed (non-string) claim degrades to None rather than rejecting
        # a token the verifier would otherwise accept; the comparison then
        # falls back to the remaining components, as the SDK documents.
        sub_claim = claims.get("sub")
        iss_claim = claims.get("iss")

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=_parse_scopes(claims.get("scope")),
            # exp is an RFC 7519 NumericDate (may be fractional); AccessToken
            # wants an int.
            expires_at=int(exp),
            resource=self._resource,
            subject=sub_claim if isinstance(sub_claim, str) else None,
            # Only `iss` is carried over. The rest of the validated payload
            # (email, name, groups) has no consumer here, and `AccessToken` is
            # reachable off `request.scope["user"]` from anything in the ASGI
            # stack, so copying the whole claim set would widen what that
            # exposes for no gain.
            claims={"iss": iss_claim} if isinstance(iss_claim, str) else None,
        )


# The (verifier, auth) pair the server threads into the SDK for the
# resource-server profile: the inbound bearer verifier and the SDK's matching
# AuthSettings (RFC 9728 metadata + the 401 challenge).
ResourceServerAuth = tuple[JwtTokenVerifier, SdkAuthSettings]


def build_resource_server_auth(
    resource: ResourceServer,
    jwt_validation: JwtValidationSettings,
    *,
    issuer_url: str,
    required_scopes: list[str] | None = None,
) -> ResourceServerAuth:
    """Build the inbound bearer verifier and the SDK auth config for ``resource``.

    Called only when the resource-server profile is active: the composition root
    parses the configured ``resource_server_url`` into ``resource`` and resolves the
    inbound ``issuer_url`` (gating on both, so an unresolvable issuer fails fast at
    the root). This receives an already-parsed identity and a resolved issuer and just
    wires them onto the validator and the SDK's ``AuthSettings``.
    """
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
    auth = SdkAuthSettings(
        issuer_url=issuer_url,
        resource_server_url=resource.url,
        required_scopes=required_scopes,
    )
    return verifier, auth
