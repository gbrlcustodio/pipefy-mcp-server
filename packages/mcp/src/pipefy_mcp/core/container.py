from __future__ import annotations

import asyncio
import logging

from pipefy_auth import (
    STORED_SESSION_TIER,
    RefreshError,
    configure_keychain_backend,
    ensure_fresh_session,
    missing_auth_message,
    resolve_pipefy_auth,
    tier_for,
)
from pipefy_sdk import PipefyClient

from pipefy_mcp._docs import DOCS_SETUP_REF
from pipefy_mcp.settings import Settings

logger = logging.getLogger(__name__)


class ServicesContainer:
    """Holds the services a request needs, built once per server lifespan.

    The server lifespan constructs one of these, initializes it, and yields it as
    the request ``lifespan_context``; tools read the client off it via
    ``get_pipefy_client``. It is a plain per-lifespan object, not a singleton.
    """

    def __init__(self) -> None:
        self.pipefy_client: PipefyClient | None = None

    async def initialize_services(self, settings: Settings) -> None:
        """Create and wire all services.

        When the resolved auth tier is the keychain-backed stored session,
        :func:`ensure_fresh_session` is invoked eagerly so a stale or revoked
        session surfaces at server startup rather than on first tool call.

        Args:
            settings: Application settings with Pipefy credentials.
        """
        # Swap the keyring backend before any keychain probe (no-op when ``auto``).
        configure_keychain_backend(settings.auth.keychain_backend)
        oidc_client = settings.auth.to_oidc_client()
        resolved = resolve_pipefy_auth(
            static_token=settings.auth.static_token,
            service_account=settings.auth.to_service_account(),
            oidc_client=oidc_client,
        )
        if resolved is None:
            raise RuntimeError(
                f"{missing_auth_message()} "
                f"See {DOCS_SETUP_REF} for host-specific install steps."
            )
        # ``oidc_client`` is None only when ``disable_stored_session`` is set;
        # the resolver then can't return STORED_SESSION_TIER, so this branch is
        # unreachable in that case.
        if tier_for(resolved) == STORED_SESSION_TIER:
            if oidc_client is None:
                raise RuntimeError(
                    "STORED_SESSION_TIER resolved without an OIDC client "
                    "(resolver invariant broken)."
                )
            try:
                await asyncio.to_thread(
                    ensure_fresh_session,
                    issuer=oidc_client.issuer_url,
                    client_id=oidc_client.client_id,
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
        self.pipefy_client = PipefyClient(
            settings=settings.pipefy, auth=resolved, surface="mcp"
        )
