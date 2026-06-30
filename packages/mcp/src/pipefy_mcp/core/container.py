from __future__ import annotations

import asyncio
import logging

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
        # The variant carries a non-None oidc_client by construction, so the
        # stored-session tier needs no separate presence check here.
        if isinstance(resolved, StoredSessionAuth):
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
        self.pipefy_client = PipefyClient(
            settings=settings.pipefy, auth=build_httpx_auth(resolved), surface="mcp"
        )
