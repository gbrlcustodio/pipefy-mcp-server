from __future__ import annotations

from dataclasses import dataclass

from httpx import Auth
from pipefy_auth import (
    build_httpx_auth,
    configure_keychain_backend,
    missing_auth_message,
    resolve_pipefy_auth,
)
from pipefy_sdk import PipefyClient

from pipefy_mcp._docs import DOCS_SETUP_REF
from pipefy_mcp.auth.request_identity import RequestContextBearerAuth
from pipefy_mcp.auth.resource_server import (
    ResourceServerAuth,
    build_resource_server_auth,
)
from pipefy_mcp.settings import Settings


@dataclass(frozen=True)
class StartupIdentity:
    """One credential resolved from settings at startup; every call runs as it.

    The stdio/local profile: with no inbound bearer, the highest-precedence
    configured credential is resolved once (via :meth:`from_configured_credential`)
    and the one shared client acts as it on every call.
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


@dataclass(frozen=True)
class RequestScopedIdentity:
    """The shared client acts per request as the calling user (hosted profile).

    ``auth`` reads the validated bearer from the request context on each outbound
    call, so one shared client serves every concurrent caller as themselves.
    """

    auth: RequestContextBearerAuth


# The client's identity source, chosen by profile at the composition root
# (:meth:`McpRuntime.for_profile`): each variant carries the ``httpx.Auth`` the one
# shared client applies to every outbound call. Both arms speak that one contract,
# so the runtime wires the client uniformly with no per-variant branching.
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
    """The MCP server's application-scoped runtime: the composition root that owns the shared client.

    Built once at server startup via :meth:`for_profile`, which turns the resolved
    settings into wired resources: the outbound identity (whose ``httpx.Auth`` backs
    the one shared :class:`PipefyClient`) and, under the ``remote`` profile, the
    inbound resource-server ``(verifier, auth)`` pair FastMCP uses to validate each
    caller's bearer.

    Wiring the client here is safe off the event loop: :class:`PipefyClient`
    construction does no network I/O and binds nothing to a running loop (its
    executors open a fresh per-request transport at call time), so the client
    built at startup works on whatever loop later serves requests.

    This is a stepping stone toward a single per-app runtime; today it owns the
    shared client and the inbound-auth pair.
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
        # Both variants expose ``.auth`` (see :data:`AuthSource`), so the client is
        # wired once here; the hosted adapter applies per-caller identity itself.
        self.pipefy_client: PipefyClient = PipefyClient(
            settings=settings.pipefy, auth=identity.auth, surface="mcp"
        )

    @classmethod
    def for_profile(cls, settings: Settings) -> McpRuntime:
        """Build the runtime for the resolved profile, wiring inbound and outbound auth.

        The composition root's one build step: ``settings.mcp.profile`` selects the
        outbound identity and, for ``remote``, the inbound resource-server pair.

        ``remote`` acts on behalf of each caller: it validates a per-request bearer
        (the inbound ``(verifier, auth)`` pair) and the shared client replays that
        caller's bearer per call (:class:`RequestScopedIdentity`). A configured
        resource server is mandatory there, so this fails fast when none resolves,
        rather than serve an open endpoint or silently fall back to a startup
        credential.

        Every other profile (stdio, or ``local`` over loopback HTTP) has no inbound
        identity: the one startup credential is resolved from settings (and fails
        fast when none is configured) and the shared client acts as it on every call.
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
            return cls(
                settings,
                RequestScopedIdentity(RequestContextBearerAuth()),
                inbound_auth=inbound_auth,
            )
        return cls(settings, StartupIdentity.from_configured_credential(settings))

    @property
    def settings(self) -> Settings:
        """The resolved settings this runtime was built from."""
        return self._settings
