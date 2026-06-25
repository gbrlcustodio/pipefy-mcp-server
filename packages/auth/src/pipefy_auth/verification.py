"""Inbound bearer validation: verify an RS256 access token against issuer JWKS.

The outbound side of this package (``bearer.py``) attaches a bearer to requests
this process makes. This is the inbound counterpart: when the process acts as an
OAuth 2.0 resource server, it must validate the access token a caller presents
before trusting it. :class:`JwtValidator` checks the token's signature against
the issuer's JWKS and its issuer, expiry, and (optionally) audience, returning
the decoded claims.

The validator is transport-agnostic and returns raw claims; mapping those claims
onto a consumer's identity type (e.g. an MCP ``AccessToken``) is the consumer's
job. It is synchronous (PyJWT and ``PyJWKClient`` are); an async consumer should
offload :meth:`JwtValidator.validate` to a thread.
"""

from __future__ import annotations

import threading
from typing import Any

import jwt
from jwt import PyJWKClient
from pipefy_infra import security

from pipefy_auth.discovery import DiscoveryPolicy, fetch_provider_metadata

_ALGORITHMS = ["RS256"]


class TokenValidationError(ValueError):
    """An inbound bearer failed validation (bad signature, issuer, expiry, aud).

    Subclasses :class:`ValueError` so a consumer that rejects on validation
    failure can catch the broad type without importing PyJWT's exception
    hierarchy. The underlying cause is chained for diagnostics.
    """


class JwtValidator:
    """Validate an RS256 access token against an issuer's JWKS.

    When an explicit ``jwks_uri`` override is supplied it is validated and the
    :class:`~jwt.PyJWKClient` is built at construction (no network). Otherwise the
    JWKS URL is resolved from the issuer's OIDC discovery document lazily, on the
    first :meth:`validate`, so construction does no network I/O and process boot
    never blocks on the IdP. A failed discovery is not cached, so the next
    ``validate`` retries (the validator self-heals once the IdP is reachable). The
    underlying ``PyJWKClient`` caches signing keys across calls.

    ``verify_audience`` is off by default: the same-audience interim runs before
    the IdP issues an ``aud`` claim. Turn it on once the audience mapper is in
    place; ``audience`` is then required by the caller.
    """

    def __init__(
        self,
        *,
        issuer_url: str,
        audience: str | None,
        verify_audience: bool,
        allow_insecure_urls: bool = False,
        jwks_uri: str | None = None,
    ) -> None:
        self._issuer = issuer_url
        self._audience = audience
        self._verify_audience = verify_audience
        self._allow_insecure_urls = allow_insecure_urls
        # Guards the one-time lazy discovery in _jwks_client: validate() can run
        # concurrently, and a cold burst should resolve jwks_uri once rather than
        # each request firing its own discovery fetch at the IdP.
        self._lock = threading.Lock()
        if jwks_uri is not None:
            # Explicit override: validated and built eagerly (no network) so a
            # misconfigured override fails at startup, not on the first request.
            resolved_jwks_uri = self._validate_jwks_uri(
                jwks_uri, allow_insecure_urls=allow_insecure_urls
            )
            # cache_keys memoizes get_signing_key(kid), so the steady-state path is
            # a dict lookup; without it every validate() rebuilds the JWK set and
            # reconstructs each RSA public key (the network fetch is cached anyway).
            self._jwks: PyJWKClient | None = PyJWKClient(
                resolved_jwks_uri, cache_keys=True
            )
        else:
            self._jwks = None

    @staticmethod
    def _validate_jwks_uri(jwks_uri: str, *, allow_insecure_urls: bool) -> str:
        """Apply the https/SSRF gate to an explicit ``jwks_uri`` override.

        The discovery path reaches the IdP through
        :func:`fetch_provider_metadata`, which enforces this gate on the issuer
        before trusting its advertised ``jwks_uri``. An explicit override skips
        discovery, so the primitive enforces the same invariant here rather than
        handing an unchecked key-fetch URL (``http://`` or an internal host) to
        :class:`~jwt.PyJWKClient`. A realm path is allowed; only a query or
        fragment is rejected.
        """
        return security.sanitize_url(
            jwks_uri, field_label="jwks_uri", allow_insecure=allow_insecure_urls
        )

    def _jwks_client(self) -> PyJWKClient:
        """Return the JWKS client, resolving it via discovery on first use.

        A discovery failure raises without assigning ``self._jwks``, so the next
        call retries rather than caching the failure. The pre-lock read is the
        fast path: once resolved, every call returns without taking the lock.
        """
        client = self._jwks
        if client is not None:
            return client
        with self._lock:
            if self._jwks is None:
                resolved_jwks_uri = self._discover_jwks_uri(
                    self._issuer, allow_insecure_urls=self._allow_insecure_urls
                )
                self._jwks = PyJWKClient(resolved_jwks_uri, cache_keys=True)
            return self._jwks

    @staticmethod
    def _discover_jwks_uri(issuer_url: str, *, allow_insecure_urls: bool) -> str:
        metadata = fetch_provider_metadata(
            issuer_url,
            policy=DiscoveryPolicy(allow_insecure_urls=allow_insecure_urls),
        )
        if metadata.jwks_uri is None:
            raise ValueError(
                f"OIDC discovery for {issuer_url!r} advertised no jwks_uri; supply "
                f"the signing-key endpoint explicitly."
            )
        return metadata.jwks_uri

    def validate(self, token: str) -> dict[str, Any]:
        """Return the token's claims, or raise :class:`TokenValidationError`.

        Every failure mode (bad signature, wrong issuer, expired, wrong
        audience, or an unreachable JWKS) is folded into
        :class:`TokenValidationError` so the caller has a single type to catch.
        """
        try:
            signing_key = self._jwks_client().get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=_ALGORITHMS,
                issuer=self._issuer,
                audience=self._audience if self._verify_audience else None,
                # require exp so a token that simply omits it is rejected rather
                # than treated as never-expiring (PyJWT only checks exp when present).
                options={"verify_aud": self._verify_audience, "require": ["exp"]},
            )
        except Exception as exc:
            raise TokenValidationError(str(exc)) from exc
