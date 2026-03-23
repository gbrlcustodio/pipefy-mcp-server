from __future__ import annotations

from typing import Self

from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.services.pipefy.ai_agent_service import AiAgentService
from pipefy_mcp.services.pipefy.ai_automation_service import AiAutomationService
from pipefy_mcp.services.pipefy.internal_api_client import InternalApiClient
from pipefy_mcp.settings import Settings


class ServicesContainer:
    """Container for all services."""

    _instance: Self | None = None
    pipefy_client: PipefyClient | None = None
    internal_api_client: InternalApiClient | None = None
    ai_automation_service: AiAutomationService | None = None
    ai_agent_service: AiAgentService | None = None

    @classmethod
    def get_instance(cls) -> Self:
        """Get the singleton instance of the container."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize the container."""
        pass

    def initialize_services(self, settings: Settings) -> None:
        """Create and wire all services.

        Args:
            settings: Application settings with Pipefy credentials.
        """
        self.pipefy_client = PipefyClient(settings=settings.pipefy)

        oauth_url = settings.pipefy.oauth_url
        oauth_client = settings.pipefy.oauth_client
        oauth_secret = settings.pipefy.oauth_secret

        if oauth_url and oauth_client and oauth_secret:
            self.internal_api_client = InternalApiClient(
                url=settings.pipefy.internal_api_url,
                oauth_url=oauth_url,
                oauth_client=oauth_client,
                oauth_secret=oauth_secret,
            )
            self.ai_automation_service = AiAutomationService(
                client=self.internal_api_client
            )
            auth = OAuth2ClientCredentials(
                token_url=oauth_url,
                client_id=oauth_client,
                client_secret=oauth_secret,
            )
            self.ai_agent_service = AiAgentService(
                settings=settings.pipefy,
                auth=auth,
            )

    def shutdown(self) -> None:
        pass
