from __future__ import annotations

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
from pipefy_mcp.core.ipaas_gateway import IpaasGateway
from pipefy_mcp.settings import Settings


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
    resource-server ``(verifier, auth)`` pair the SDK uses to validate each caller's
    bearer. It owns the process-scoped :class:`PipefyEngine` (the shared endpoints and
    GraphQL schema cache, built auth-agnostic with no network I/O) and opens a cheap
    per-request session bound to the caller's identity.

    The HTTP transport's DNS-rebinding allowlist is deliberately not held here. The
    SDK takes it per transport, on ``streamable_http_app()``, so it travels with the
    serving call instead: :func:`pipefy_mcp.server.run_server` resolves it through
    :func:`pipefy_mcp.core.transport_security.transport_security_for`, and only the
    HTTP transport has anything to apply it to.

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
        self._identity = identity
        self.inbound_auth = inbound_auth
        # Narrow per-deployment facts resolved at startup. The runtime deliberately
        # holds no Settings tree: tools reach it off the request context, so
        # exposing the tree would let tool code read any process-global value at
        # call time (#405; see the "Process-global configuration" section of AGENTS.md).
        self.is_remote = settings.mcp.profile == "remote"
        self.unified_envelope = settings.mcp.unified_envelope
        self._engine = PipefyEngine.build(settings.pipefy, surface="mcp")
        # Per-deployment iPaaS wiring; None only when the operator blanks the
        # client id, and the iPaaS tools then report the capability disabled.
        self._ipaas_gateway = (
            IpaasGateway(
                url=settings.ipaas.url,
                oauth_client_id=settings.ipaas.oauth_client_id or "",
                oauth_client_secret=settings.ipaas.oauth_client_secret,
                oauth_redirect_uri=settings.ipaas.oauth_redirect_uri,
            )
            if settings.ipaas.configured
            else None
        )

    @classmethod
    def for_profile(cls, settings: Settings) -> McpRuntime:
        """Build the runtime for the resolved profile, wiring inbound and outbound auth.

        The composition root's one build step: it parses the ``resource_server_url``
        into one :class:`ResourceServer` and selects the per-profile identity from it
        (and, for ``remote``, the inbound-auth pair derived from that same resource).
        The one ``cls(...)`` call then wires the fields common to both profiles.
        """
        url = settings.rs.resource_server_url
        resource = ResourceServer.from_url(url) if url else None
        if settings.mcp.profile == "remote":
            identity, inbound_auth = cls._remote_identity(settings, resource)
        else:
            identity, inbound_auth = cls._local_identity(settings), None
        return cls(
            settings,
            identity,
            inbound_auth=inbound_auth,
        )

    @staticmethod
    def _remote_identity(
        settings: Settings, resource: ResourceServer | None
    ) -> tuple[AuthSource, ResourceServerAuth]:
        """The ``remote`` profile's identity: a per-request bearer and an inbound RS pair.

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
        return RequestScopedIdentity(), inbound_auth

    @staticmethod
    def _local_identity(settings: Settings) -> AuthSource:
        """The ``local`` profile's identity (stdio, or loopback HTTP): one startup credential.

        No inbound identity: the one startup credential is resolved from settings (and
        fails fast when none is configured) and every session acts as it.
        """
        return StartupIdentity.from_configured_credential(settings)

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
    def ipaas_gateway(self) -> IpaasGateway | None:
        """The deployment's iPaaS gateway, or None when unconfigured.

        Built once at startup from :class:`pipefy_mcp.settings.IpaasSettings`
        (a per-deployment value, identical for every caller); the gateway is
        stateless, so sharing one instance across requests holds no identity.
        """
        return self._ipaas_gateway
