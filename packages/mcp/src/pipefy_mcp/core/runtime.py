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
from pipefy_sdk import PipefyClient, PipefyEngine

from pipefy_mcp._docs import DOCS_SETUP_REF
from pipefy_mcp.auth.request_identity import require_request_bearer
from pipefy_mcp.auth.resource_server import (
    ResourceServerAuth,
    build_resource_server_auth,
)
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

    def resolve(self) -> Auth:
        return self.auth


@dataclass(frozen=True)
class RequestScopedIdentity:
    """The calling user's identity, resolved per request (hosted profile).

    :meth:`resolve` snapshots the request's validated bearer (read in the caller's
    task, where FastMCP's ``AuthContextMiddleware`` set the contextvar) into a
    static credential for that one session, so concurrent callers never share
    identity. A future auth transform (OBO exchange, a distinct downstream
    audience) is a change to what this method returns, nothing else.
    """

    def resolve(self) -> Auth:
        return StaticBearerAuth(require_request_bearer())


# The identity source for a request's session, chosen by profile at the
# composition root (:meth:`McpRuntime.for_profile`): each variant's :meth:`resolve`
# returns the ``httpx.Auth`` the per-request session binds. Both arms speak that one
# contract, so the runtime opens every session uniformly with no per-variant
# branching.
AuthSource = StartupIdentity | RequestScopedIdentity


def _login_issuer_url(settings: Settings) -> str | None:
    """The issuer this process logs into, the fallback for the inbound issuer.

    In a single-realm deployment the IdP the server authenticates against is the
    same one that mints the inbound bearers it validates, so the login issuer is
    the default when no explicit ``PIPEFY_JWT_ISSUER_URL`` override is set.
    """
    oidc_client = settings.auth.to_oidc_client()
    return oidc_client.issuer_url if oidc_client else None


class McpRuntime:
    """The MCP server's application-scoped runtime: the composition root that owns the shared engine.

    Built once at server startup via :meth:`for_profile`, which turns the resolved
    settings into wired resources: the outbound identity (whose :meth:`resolve`
    backs each request's session) and, under the ``remote`` profile, the inbound
    resource-server ``(verifier, auth)`` pair FastMCP uses to validate each caller's
    bearer. It owns the process-scoped :class:`PipefyEngine` (the shared endpoints
    and GraphQL schema cache, built auth-agnostic with no network I/O) and opens a
    cheap per-request session bound to the caller's identity.

    Building the engine here is safe off the event loop: it does no network I/O and
    binds nothing to a running loop (its endpoints open a fresh per-request
    transport at call time), so the engine built at startup serves whatever loop
    later handles requests.

    This is a stepping stone toward a single per-app runtime; today it owns the
    shared engine and the inbound-auth pair.
    """

    def __init__(
        self,
        settings: Settings,
        identity: AuthSource,
        *,
        inbound_auth: ResourceServerAuth | None = None,
    ) -> None:
        self._settings = settings
        self._identity = identity
        self.inbound_auth = inbound_auth
        self._engine = PipefyEngine.build(settings.pipefy, surface="mcp")

    @classmethod
    def for_profile(cls, settings: Settings) -> McpRuntime:
        """Build the runtime for the resolved profile, wiring inbound and outbound auth.

        The composition root's one build step: ``settings.mcp.profile`` selects the
        outbound identity and, for ``remote``, the inbound resource-server pair.

        ``remote`` acts on behalf of each caller: it validates a per-request bearer
        (the inbound ``(verifier, auth)`` pair) and each session replays that
        caller's snapshotted bearer (:class:`RequestScopedIdentity`). A configured
        resource server is mandatory there, so this fails fast when none resolves,
        rather than serve an open endpoint or silently fall back to a startup
        credential.

        Every other profile (stdio, or ``local`` over loopback HTTP) has no inbound
        identity: the one startup credential is resolved from settings (and fails
        fast when none is configured) and every session acts as it.
        """
        if settings.mcp.profile == "remote":
            inbound_auth = build_resource_server_auth(
                settings.rs,
                settings.jwt,
                default_issuer_url=_login_issuer_url(settings),
            )
            if inbound_auth is None:
                raise RuntimeError(
                    "the 'remote' profile requires a resource server: set "
                    "PIPEFY_MCP_RS_RESOURCE_SERVER_URL so the server validates a "
                    "per-request bearer and acts on behalf of the caller."
                )
            return cls(settings, RequestScopedIdentity(), inbound_auth=inbound_auth)
        return cls(settings, StartupIdentity.from_configured_credential(settings))

    def session_for_request(self) -> PipefyClient:
        """Open a session bound to the current request's identity.

        Cheap per call: it binds the identity's resolved ``auth`` to the shared
        endpoints. Under the hosted profile the identity snapshots the request's
        validated bearer, so concurrent callers each act as themselves; under the
        stdio profile it returns the one credential resolved at startup.
        """
        return self._engine.session(self._identity.resolve())

    @property
    def settings(self) -> Settings:
        """The resolved settings this runtime was built from."""
        return self._settings
