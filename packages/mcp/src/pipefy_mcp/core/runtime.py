from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

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
    """The shared client acts as one credential resolved from settings at startup.

    The stdio/local profile: with no inbound bearer, the runtime resolves the
    highest-precedence configured credential once and every call runs as it.
    """


@dataclass(frozen=True)
class RequestScopedIdentity:
    """The shared client acts per request as the calling user (hosted profile).

    ``auth`` reads the validated bearer from the request context on each outbound
    call, so one shared client serves every concurrent caller as themselves.
    """

    auth: RequestContextBearerAuth


# The client's identity model, parsed from the transport profile at the
# composition root: :func:`pipefy_mcp.server.build_pipefy_mcp_server` picks the
# variant, :meth:`McpRuntime._build_client` is total over it.
AuthStrategy = StartupIdentity | RequestScopedIdentity


class McpRuntime:
    """The MCP server's application-scoped runtime: the composition root that owns the shared client.

    Built once at server startup with the parsed :data:`AuthStrategy` the
    composition root chose. Construction is where the runtime wires its
    dependencies and fails fast: it resolves the credential (the keychain read
    behind :func:`resolve_pipefy_auth`, on the startup-identity arm) and builds
    the one shared :class:`PipefyClient`, so a missing credential surfaces at
    startup rather than on the first tool call.

    Wiring the client here is safe off the event loop: :class:`PipefyClient`
    construction does no network I/O and binds nothing to a running loop (its
    executors open a fresh per-request transport at call time), so the client
    built at startup works on whatever loop later serves requests.

    This is the stepping stone toward the single per-app runtime issue #346
    formalizes; today it owns the shared client.
    """

    def __init__(self, settings: Settings, strategy: AuthStrategy) -> None:
        self._settings = settings
        self._strategy = strategy
        self.pipefy_client: PipefyClient = self._build_client()

    def _build_client(self) -> PipefyClient:
        match self._strategy:
            case RequestScopedIdentity(auth):
                # Hosted profile: no startup credential. Each outbound call reads
                # the caller's validated bearer from the request context, so the
                # one shared client acts on behalf of whoever is calling.
                return PipefyClient(
                    settings=self._settings.pipefy, auth=auth, surface="mcp"
                )
            case StartupIdentity():
                return self._build_startup_client()
            case _:
                assert_never(self._strategy)

    def _build_startup_client(self) -> PipefyClient:
        """Resolve one credential from settings and wire the shared client to it.

        The stored-session method wires a lazily-refreshing auth
        (:class:`pipefy_auth.RefreshableBearerAuth`): the token is fetched and
        refreshed on the first request that needs it, not eagerly at startup.
        """
        settings = self._settings
        # Swap the keyring backend before any keychain probe (no-op when ``auto``).
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
        return PipefyClient(
            settings=settings.pipefy, auth=build_httpx_auth(resolved), surface="mcp"
        )
