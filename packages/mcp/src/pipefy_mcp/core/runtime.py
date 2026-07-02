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


# The client's identity source, parsed from the transport profile at the
# composition root: :func:`pipefy_mcp.server._select_auth_source` picks the
# variant, each carrying the ``httpx.Auth`` the one shared client applies to every
# outbound call. Both arms speak that one contract, so the runtime wires the
# client uniformly with no per-variant branching.
AuthSource = StartupIdentity | RequestScopedIdentity


class McpRuntime:
    """The MCP server's application-scoped runtime: the composition root that owns the shared client.

    Built once at server startup with the parsed :data:`AuthSource` the composition
    root chose. It wires the one shared :class:`PipefyClient` to that identity's
    ``httpx.Auth``; the credential (and its fail-fast) is resolved at the
    composition root, not here (see
    :meth:`StartupIdentity.from_configured_credential` and
    :func:`pipefy_mcp.server._select_auth_source`).

    Wiring the client here is safe off the event loop: :class:`PipefyClient`
    construction does no network I/O and binds nothing to a running loop (its
    executors open a fresh per-request transport at call time), so the client
    built at startup works on whatever loop later serves requests.

    This is the stepping stone toward the single per-app runtime issue #346
    formalizes; today it owns the shared client.
    """

    def __init__(self, settings: Settings, identity: AuthSource) -> None:
        self._settings = settings
        self._identity = identity
        # Both identity variants carry an ``httpx.Auth``: the startup credential
        # (stdio) or the request-context bearer adapter (hosted). Under the hosted
        # profile that adapter reads each caller's validated bearer from the
        # request context per call, so the one shared client serves every
        # concurrent caller as themselves.
        self.pipefy_client: PipefyClient = PipefyClient(
            settings=settings.pipefy, auth=identity.auth, surface="mcp"
        )
