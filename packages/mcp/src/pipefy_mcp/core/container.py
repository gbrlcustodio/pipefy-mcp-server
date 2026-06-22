from __future__ import annotations

import asyncio
import logging
from typing import Any, Self

from pipefy_auth import (
    STORED_SESSION_TIER,
    RefreshError,
    configure_keychain_backend,
    ensure_fresh_session,
    missing_auth_message,
    resolve_pipefy_auth,
    tier_for,
)
from pipefy_sdk import InternalApiClient, PipefyClient

from pipefy_mcp._docs import DOCS_SETUP_REF
from pipefy_mcp.settings import Settings

logger = logging.getLogger(__name__)


class ServicesContainer:
    """Container for all services."""

    _instance: Self | None = None

    def __init__(self) -> None:
        self.pipefy_client: PipefyClient | None = None

    @classmethod
    def get_instance(cls) -> Self:
        """Get the singleton instance of the container."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize_services(self, settings: Settings) -> None:
        """Create and wire all services.

        When the resolved auth tier is the keychain-backed stored session,
        :func:`ensure_fresh_session` is invoked eagerly so a stale or revoked
        session surfaces at server startup rather than on first tool call.

        Args:
            settings: Application settings with Pipefy credentials.
        """
        pipefy = settings.pipefy
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
        self.pipefy_client = PipefyClient(settings=pipefy, auth=resolved)
        internal_client = InternalApiClient(
            url=pipefy.internal_api_url,
            auth=resolved,
            allow_insecure_urls=pipefy.allow_insecure_urls,
        )
        self.pipefy_client.set_internal_api_client(internal_client)


class PipefyClientProxy:
    """A stable handle that always resolves the container's current client.

    Tools capture this once, at registration, instead of a concrete
    :class:`PipefyClient`. Each attribute access forwards to the live
    ``container.pipefy_client``, so re-initializing services (which builds a
    fresh client) is picked up without re-registering tools. This is what lets
    registration happen once at construction rather than inside the lifespan.
    """

    def __init__(self, container: ServicesContainer) -> None:
        self._container = container

    def __getattr__(self, name: str) -> Any:
        # ``_container`` is a real instance attribute, so it never routes here;
        # any other attribute is delegated to the live client.
        client = self._container.pipefy_client
        if client is None:
            raise RuntimeError(
                "Pipefy client is not initialized; the server lifespan must "
                "initialize services before any tool is invoked."
            )
        return getattr(client, name)
