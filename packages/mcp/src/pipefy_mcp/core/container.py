from __future__ import annotations

from typing import Self

from pipefy_auth import (
    missing_auth_message,
    resolve_pipefy_auth,
)
from pipefy_sdk import AiAutomationService, InternalApiClient, PipefyClient

from pipefy_mcp.settings import Settings


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

    def initialize_services(self, settings: Settings) -> None:
        """Create and wire all services.

        Args:
            settings: Application settings with Pipefy credentials.
        """
        pipefy = settings.pipefy
        # The stored-session tier is wired in a follow-up against #213.
        resolved = resolve_pipefy_auth(
            static_token=settings.auth.static_token,
            service_account=settings.auth.to_service_account(),
        )
        if resolved is None:
            raise RuntimeError(missing_auth_message())
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
