from __future__ import annotations

from mcp.server.transport_security import TransportSecuritySettings
from pipefy_sdk import PipefyClient, PipefyEngine
from starlette.requests import Request

from pipefy_mcp.auth import (
    AuthSource,
    RequestScopedIdentity,
    ResourceServer,
    ResourceServerAuth,
    StartupIdentity,
    build_resource_server_auth,
)
from pipefy_mcp.core.transport_security import build_transport_security
from pipefy_mcp.settings import ResourceServerSettings, Settings


def _resource_server(rs: ResourceServerSettings) -> ResourceServer | None:
    """Parse the configured resource-server URL into its value object, or ``None``.

    The one place the resource identity is parsed: the composition root feeds this
    single :class:`ResourceServer` to both consumers (inbound auth and the transport
    allowlist), so neither re-parses the URL and they cannot disagree on the host.
    """
    url = rs.resource_server_url
    return ResourceServer.from_url(url) if url else None


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
    backs each request's session), the HTTP transport's DNS-rebinding allowlist, and,
    under the ``remote`` profile, the inbound resource-server ``(verifier, auth)`` pair
    FastMCP uses to validate each caller's bearer. It parses the ``resource_server_url``
    into one :class:`ResourceServer` and feeds it to both the inbound-auth and the
    allowlist builders, so they cannot disagree on the resource host. It owns the
    process-scoped :class:`PipefyEngine` (the shared endpoints and GraphQL schema cache,
    built auth-agnostic with no network I/O) and opens a cheap per-request session bound
    to the caller's identity.

    Building the engine here is safe off the event loop: it does no network I/O and
    binds nothing to a running loop (its endpoints open a fresh per-request
    transport at call time), so the engine built at startup serves whatever loop
    later handles requests.

    This is a stepping stone toward a single per-app runtime; today it owns the
    shared engine, the inbound-auth pair, and the transport allowlist.
    """

    def __init__(
        self,
        settings: Settings,
        identity: AuthSource,
        *,
        inbound_auth: ResourceServerAuth | None = None,
        transport_security: TransportSecuritySettings | None = None,
    ) -> None:
        self._settings = settings
        self._identity = identity
        self.inbound_auth = inbound_auth
        self.transport_security = transport_security
        self._engine = PipefyEngine.build(settings.pipefy, surface="mcp")

    @classmethod
    def for_profile(cls, settings: Settings) -> McpRuntime:
        """Build the runtime for the resolved profile, wiring inbound and outbound auth.

        The composition root's one build step: it parses the ``resource_server_url``
        once, builds the transport allowlist from that one parsed resource, and hands
        both to the per-profile builder ``settings.mcp.profile`` selects. Parsing here
        keeps the resource a single value both the allowlist and (for ``remote``) the
        inbound-auth pair are derived from, so they cannot disagree on the host.
        """
        resource = _resource_server(settings.rs)
        transport_security = build_transport_security(settings.mcp, resource)
        if settings.mcp.profile == "remote":
            return cls._for_remote_profile(settings, resource, transport_security)
        return cls._for_local_profile(settings, transport_security)

    @classmethod
    def _for_remote_profile(
        cls,
        settings: Settings,
        resource: ResourceServer | None,
        transport_security: TransportSecuritySettings | None,
    ) -> McpRuntime:
        """The ``remote`` profile: a per-request identity and an inbound RS pair.

        ``remote`` acts on behalf of each caller: it validates a per-request bearer
        (the inbound ``(verifier, auth)`` pair) and each session replays that caller's
        snapshotted bearer (:class:`RequestScopedIdentity`). A resource server and a
        resolvable inbound issuer are both mandatory here, so this gates on each and
        fails fast rather than serve an open endpoint or silently fall back to a
        startup credential.
        """
        if resource is None:
            raise RuntimeError(
                "the 'remote' profile requires a resource server: set "
                "PIPEFY_MCP_RS_RESOURCE_SERVER_URL so the server validates a "
                "per-request bearer and acts on behalf of the caller."
            )
        # The inbound issuer is the explicit PIPEFY_JWT_ISSUER_URL override, else the
        # login issuer this process authenticates against; with neither, the bearers
        # cannot be validated, so refuse to build rather than serve an open endpoint.
        issuer_url = settings.jwt.resolve_issuer_url(_login_issuer_url(settings))
        if issuer_url is None:
            raise RuntimeError(
                "the 'remote' profile requires an inbound issuer: set "
                "PIPEFY_JWT_ISSUER_URL, or leave the stored-session login enabled so "
                "its issuer can be reused."
            )
        inbound_auth = build_resource_server_auth(
            resource,
            settings.jwt,
            issuer_url=issuer_url,
            required_scopes=settings.rs.required_scopes,
        )
        return cls(
            settings,
            RequestScopedIdentity(),
            inbound_auth=inbound_auth,
            transport_security=transport_security,
        )

    @classmethod
    def _for_local_profile(
        cls,
        settings: Settings,
        transport_security: TransportSecuritySettings | None,
    ) -> McpRuntime:
        """The ``local`` profile (stdio, or loopback HTTP): one startup credential.

        No inbound identity: the one startup credential is resolved from settings (and
        fails fast when none is configured) and every session acts as it.
        """
        return cls(
            settings,
            StartupIdentity.from_configured_credential(settings),
            transport_security=transport_security,
        )

    def session_for_request(self, request: Request | None) -> PipefyClient:
        """Open a session bound to the current request's identity.

        Cheap per call: it binds the identity's resolved ``auth`` to the shared
        endpoints. Under the hosted profile the identity snapshots the bearer off
        ``request`` (the message's own validated request, passed down from the tool
        handler), so concurrent callers each act as themselves; under the stdio
        profile the identity ignores it and returns the one startup credential.
        """
        return self._engine.session(self._identity.resolve(request))

    @property
    def settings(self) -> Settings:
        """The resolved settings this runtime was built from."""
        return self._settings
