from unittest.mock import Mock, patch

import pytest
from pipefy_auth import AuthSettings, StaticBearerAuth
from pipefy_sdk import PipefyClient, PipefySettings

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.settings import Settings

_AUTH_ENV_KEYS = (
    "PIPEFY_TOKEN",
    "PIPEFY_SERVICE_ACCOUNT_URL",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET",
    "PIPEFY_OAUTH_URL",
    "PIPEFY_OAUTH_CLIENT",
    "PIPEFY_OAUTH_SECRET",
    "PIPEFY_AUTH_URL",
)


def _service_account_auth_settings() -> AuthSettings:
    return AuthSettings(
        service_account_url="https://auth.pipefy.com/oauth/token",
        service_account_client_id="client_id",
        service_account_client_secret="client_secret",
    )


class TestServicesContainer:
    """Test cases for ServicesContainer"""

    @pytest.fixture(autouse=True)
    def clear_auth_env(self, monkeypatch):
        """Strip ambient ``PIPEFY_*`` auth env so ``AuthSettings()`` is hermetic."""
        for key in _AUTH_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before and after each test"""
        ServicesContainer._instance = None
        yield
        ServicesContainer._instance = None

    def test_get_instance_returns_singleton(self):
        """Test that get_instance returns the same instance"""

        instance1 = ServicesContainer.get_instance()
        instance2 = ServicesContainer.get_instance()

        assert instance1 is instance2
        assert isinstance(instance1, ServicesContainer)

    def test_get_instance_creates_new_instance_when_none(self):
        """Test that get_instance creates a new instance when _instance is None"""

        instance = ServicesContainer.get_instance()

        assert instance is not None
        assert isinstance(instance, ServicesContainer)
        assert ServicesContainer._instance is instance

    def test_init_initializes_empty_container(self):
        """Test that __init__ creates an empty container"""
        container = ServicesContainer()

        assert container.pipefy_client is None

    @patch("pipefy_mcp.core.container.AiAutomationService")
    @patch("pipefy_mcp.core.container.InternalApiClient")
    @patch("pipefy_mcp.core.container.PipefyClient")
    def test_initialize_services_creates_pipefy_client(
        self,
        mock_pipefy_client_class,
        mock_internal_api_client_class,
        mock_ai_automation_service_class,
    ):
        """Test that initialize_services creates and assigns PipefyClient"""
        mock_client = Mock(spec=PipefyClient)
        mock_client.client = Mock()
        mock_pipefy_client_class.return_value = mock_client

        settings = Settings(
            pipefy=PipefySettings(graphql_url="https://api.pipefy.com/graphql"),
            auth=_service_account_auth_settings(),
        )

        container = ServicesContainer()
        container.initialize_services(settings)

        mock_pipefy_client_class.assert_called_once()
        kwargs = mock_pipefy_client_class.call_args.kwargs
        assert kwargs["settings"] is settings.pipefy
        assert "auth" in kwargs
        assert container.pipefy_client is mock_client

    @patch("pipefy_mcp.core.container.InternalApiClient")
    @patch("pipefy_mcp.core.container.AiAutomationService")
    @patch("pipefy_mcp.core.container.PipefyClient")
    def test_initialize_services_creates_ai_services(
        self,
        mock_pipefy_client_class,
        mock_ai_automation_service_class,
        mock_internal_api_client_class,
    ):
        mock_client = Mock(spec=PipefyClient)
        mock_client.client = Mock()
        mock_pipefy_client_class.return_value = mock_client

        settings = Settings(
            pipefy=PipefySettings(graphql_url="https://api.pipefy.com/graphql"),
            auth=_service_account_auth_settings(),
        )

        container = ServicesContainer()
        container.initialize_services(settings)

        mock_internal_api_client_class.assert_called_once()
        mock_ai_automation_service_class.assert_called_once()
        mock_client.set_ai_automation_service.assert_called_once_with(
            mock_ai_automation_service_class.return_value
        )

    @patch("pipefy_mcp.core.container.AiAutomationService")
    @patch("pipefy_mcp.core.container.InternalApiClient")
    @patch("pipefy_mcp.core.container.PipefyClient")
    def test_initialize_services_picks_up_pipefy_token_over_service_account(
        self,
        mock_pipefy_client_class,
        mock_internal_api_client_class,
        mock_ai_automation_service_class,
    ):
        """``PIPEFY_TOKEN`` outranks ``PIPEFY_SERVICE_ACCOUNT_*`` (same precedence as the CLI).

        Also asserts that the bearer path wires ``InternalApiClient`` +
        ``AiAutomationService`` with the SAME ``auth`` instance
        ``PipefyClient`` got, so GraphQL auth and AI automation can't drift.
        """
        mock_client = Mock(spec=PipefyClient)
        mock_client.client = Mock()
        mock_pipefy_client_class.return_value = mock_client
        settings = Settings(
            pipefy=PipefySettings(graphql_url="https://api.pipefy.com/graphql"),
            auth=AuthSettings(
                static_token="env-bearer",
                service_account_url="https://auth.pipefy.com/oauth/token",
                service_account_client_id="client_id",
                service_account_client_secret="client_secret",
            ),
        )
        ServicesContainer().initialize_services(settings)
        pc_auth = mock_pipefy_client_class.call_args.kwargs["auth"]
        assert isinstance(pc_auth, StaticBearerAuth)
        mock_internal_api_client_class.assert_called_once()
        assert mock_internal_api_client_class.call_args.kwargs["auth"] is pc_auth
        mock_ai_automation_service_class.assert_called_once()
        mock_client.set_ai_automation_service.assert_called_once_with(
            mock_ai_automation_service_class.return_value
        )

    @patch("pipefy_mcp.core.container.AiAutomationService")
    @patch("pipefy_mcp.core.container.InternalApiClient")
    @patch("pipefy_mcp.core.container.PipefyClient")
    def test_initialize_services_raises_when_no_auth_source_configured(
        self,
        mock_pipefy_client_class,
        mock_internal_api_client_class,
        mock_ai_automation_service_class,
    ):
        """No PIPEFY_TOKEN and no service-account triple → runtime error."""
        settings = Settings(
            pipefy=PipefySettings(graphql_url="https://api.pipefy.com/graphql"),
            auth=AuthSettings(),
        )
        with pytest.raises(RuntimeError, match="Missing Pipefy authentication"):
            ServicesContainer().initialize_services(settings)
