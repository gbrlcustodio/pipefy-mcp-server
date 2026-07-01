from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import assert_never

from pipefy_auth import (
    RefreshError,
    StoredSessionAuth,
    build_httpx_auth,
    configure_keychain_backend,
    ensure_fresh_session,
    missing_auth_message,
    resolve_pipefy_auth,
)
from pipefy_sdk import PipefyClient

from pipefy_mcp._docs import DOCS_SETUP_REF
from pipefy_mcp.auth.request_identity import RequestContextBearerAuth
from pipefy_mcp.settings import Settings

logger = logging.getLogger(__name__)


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
# variant, :meth:`McpRuntime.initialize` is total over it.
AuthStrategy = StartupIdentity | RequestScopedIdentity


class McpRuntime:
    """The MCP server's application-scoped runtime: built once, holds the shared client.

    Constructed at server startup with the parsed :data:`AuthStrategy` the
    composition root chose. Construction is pure (no I/O); :meth:`initialize`
    runs the effects (keychain reads, building the client) and is idempotent, so
    the Streamable HTTP lifespan can re-enter it per session without rebuilding.
    The build binds per-request httpx clients to the running loop, so it happens
    in :meth:`initialize` (in the serving loop), not at construction.

    This is the stepping stone toward the single per-app runtime issue #346
    formalizes; today it owns the shared :class:`PipefyClient`.
    """

    def __init__(self, settings: Settings, strategy: AuthStrategy) -> None:
        self._settings = settings
        self._strategy = strategy
        self._lock = asyncio.Lock()
        self.pipefy_client: PipefyClient | None = None

    async def initialize(self) -> None:
        """Build the shared Pipefy client once; a no-op on later calls.

        Idempotent: Streamable HTTP re-enters the lifespan per session, and every
        session shares the one client built on the first entry. Later entries take
        the pre-lock fast path and never touch the lock. The lock only guards the
        first build, making concurrent first entries safe: the loser re-checks and
        sees the client already built.
        """
        if self.pipefy_client is not None:
            return
        async with self._lock:
            if self.pipefy_client is not None:
                return
            self.pipefy_client = await self._build_client()

    async def _build_client(self) -> PipefyClient:
        match self._strategy:
            case RequestScopedIdentity(auth):
                # Hosted profile: no startup credential. Each outbound call reads
                # the caller's validated bearer from the request context, so the
                # one shared client acts on behalf of whoever is calling.
                return PipefyClient(
                    settings=self._settings.pipefy, auth=auth, surface="mcp"
                )
            case StartupIdentity():
                return await self._build_startup_client()
            case _:
                assert_never(self._strategy)

    async def _build_startup_client(self) -> PipefyClient:
        """Resolve one credential from settings and wire the shared client to it.

        When the resolved auth method is the keychain-backed stored session,
        :func:`ensure_fresh_session` runs eagerly so a stale or revoked session
        surfaces at server startup rather than on the first tool call.
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
        if isinstance(resolved, StoredSessionAuth):
            await self._warm_up_stored_session(resolved)
        return PipefyClient(
            settings=settings.pipefy, auth=build_httpx_auth(resolved), surface="mcp"
        )

    async def _warm_up_stored_session(self, resolved: StoredSessionAuth) -> None:
        try:
            await asyncio.to_thread(
                ensure_fresh_session,
                issuer=resolved.oidc_client.issuer_url,
                client_id=resolved.oidc_client.client_id,
            )
        except RefreshError as exc:
            logger.error(
                "Stored Pipefy session could not be refreshed at startup: %s. "
                "Run `pipefy auth login` to sign in again; see %s for "
                "host-specific alternatives.",
                exc,
                DOCS_SETUP_REF,
            )
            raise
        logger.info("Pipefy stored session warmed up at startup")
