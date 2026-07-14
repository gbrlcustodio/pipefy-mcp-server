"""Outbound identity for a request's SDK session: who each session acts as.

The counterpart to :mod:`pipefy_mcp.auth.inbound_identity` (which extracts the
*inbound* bearer a caller presents): these types resolve the *outbound*
``httpx.Auth`` the per-request SDK session binds. The two profiles pick a
different variant at the composition root, and both speak one ``resolve`` contract
so the runtime opens every session uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass

from httpx import Auth
from pipefy_auth import (
    StaticBearerAuth,
    build_httpx_auth,
    configure_keychain_backend,
    missing_auth_message,
    resolve_pipefy_auth,
)
from starlette.requests import Request

from pipefy_mcp._docs import DOCS_SETUP_REF
from pipefy_mcp.auth.inbound_identity import require_request_bearer
from pipefy_mcp.settings import Settings


@dataclass(frozen=True)
class StartupIdentity:
    """One credential resolved from settings at startup; every request runs as it.

    The stdio/local profile: with no inbound bearer, the composition root resolves
    the highest-precedence configured credential once (via
    :meth:`from_configured_credential`); :meth:`resolve` returns that same
    credential for every session.
    """

    auth: Auth

    @classmethod
    def from_configured_credential(cls, settings: Settings) -> StartupIdentity:
        """Resolve the one startup credential from settings, or fail fast.

        Swaps the keyring backend (no-op when ``auto``), resolves the
        highest-precedence configured credential (the keychain read behind
        :func:`resolve_pipefy_auth`), and raises when none is configured so a
        missing credential surfaces at startup rather than on the first tool call.

        The resolved auth refreshes lazily (a stored session wires
        :class:`pipefy_auth.RefreshableBearerAuth`): the token is fetched and
        refreshed on the first request that needs it, not eagerly here.
        """
        configure_keychain_backend(settings.auth.keychain_backend)
        resolved = resolve_pipefy_auth(
            static_token=settings.auth.static_token,
            service_account=settings.auth.to_service_account(),
            oidc_client=settings.auth.to_oidc_client(),
        )
        if resolved is None:
            raise RuntimeError(
                f"{missing_auth_message()} "
                f"See {DOCS_SETUP_REF} for host-specific install steps."
            )
        return cls(build_httpx_auth(resolved))

    def resolve(self, request: Request | None) -> Auth:
        # The startup credential is request-independent; the request the runtime
        # threads through for the hosted profile has nothing to resolve here.
        return self.auth


@dataclass(frozen=True)
class RequestScopedIdentity:
    """The calling user's identity, resolved per request (hosted profile).

    :meth:`resolve` snapshots the validated bearer off the ``request`` the tool
    handler passes in into a static credential for that one session, so concurrent
    callers never share identity. Reading the request the handler received (rather
    than ``auth_context_var``, which stateful Streamable HTTP freezes at the
    session's first bearer) is what keeps the snapshot on the current caller. A
    future auth transform (OBO exchange, a distinct downstream audience) is a change
    to what this method returns, nothing else.
    """

    def resolve(self, request: Request | None) -> Auth:
        return StaticBearerAuth(require_request_bearer(request))


# The identity source for a request's session, chosen by profile at the
# composition root (:meth:`pipefy_mcp.core.runtime.McpRuntime.for_profile`): each
# variant's :meth:`resolve` takes the in-flight request and returns the
# ``httpx.Auth`` the per-request session binds. Both arms speak that one contract,
# so the runtime opens every session uniformly with no per-variant branching.
AuthSource = StartupIdentity | RequestScopedIdentity


__all__ = ["AuthSource", "RequestScopedIdentity", "StartupIdentity"]
