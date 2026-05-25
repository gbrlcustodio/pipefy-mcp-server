from __future__ import annotations

import asyncio
import logging
from typing import Self

from pipefy_auth import (
    STORED_SESSION_TIER,
    RefreshError,
    ensure_fresh_session,
    missing_auth_message,
    resolve_pipefy_auth,
    tier_for,
)
from pipefy_sdk import AiAutomationService, InternalApiClient, PipefyClient

from pipefy_mcp.settings import Settings

logger = logging.getLogger(__name__)


class ServicesContainer:
    """Container for all services."""

    _instance: Self | None = None
    pipefy_client: PipefyClient | None = None

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
        oidc_client = settings.auth.to_oidc_client()
        resolved = resolve_pipefy_auth(
            static_token=settings.auth.static_token,
            service_account=settings.auth.to_service_account(),
            oidc_client=oidc_client,
        )
        if resolved is None:
            raise RuntimeError(missing_auth_message())
        if oidc_client is not None and tier_for(resolved) == STORED_SESSION_TIER:
            try:
                await asyncio.to_thread(
                    ensure_fresh_session,
                    issuer=oidc_client.issuer_url,
                    client_id=oidc_client.client_id,
                )
            except RefreshError as exc:
                logger.error(
                    "Stored Pipefy session could not be refreshed at startup: %s. "
                    "Run `pipefy auth login` to sign in again.",
                    exc,
                )
                raise
            logger.info("Pipefy stored session warmed up at startup")
        self.pipefy_client = PipefyClient(settings=pipefy, auth=resolved)
        if pipefy.internal_api_url:
            internal_client = InternalApiClient(
                url=pipefy.internal_api_url,
                auth=resolved,
                allow_insecure_urls=pipefy.allow_insecure_urls,
            )
            self.pipefy_client.set_internal_api_client(internal_client)
            self.pipefy_client.set_ai_automation_service(
                AiAutomationService(client=internal_client)
            )
