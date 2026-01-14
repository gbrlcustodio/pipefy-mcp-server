from unittest.mock import Mock, patch

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.settings import PipefySettings, Settings


class TestServicesContainer:
    """Test cases for ServicesContainer"""

    def test_get_instance_returns_singleton(self):
        """Test that get_instance returns the same instance"""
        # Reset singleton for test
        ServicesContainer._instance = None

        instance1 = ServicesContainer.get_instance()
        instance2 = ServicesContainer.get_instance()

        assert instance1 is instance2
        assert isinstance(instance1, ServicesContainer)

    def test_get_instance_creates_new_instance_when_none(self):
        """Test that get_instance creates a new instance when _instance is None"""
        # Reset singleton for test
        ServicesContainer._instance = None

        instance = ServicesContainer.get_instance()

        assert instance is not None
        assert isinstance(instance, ServicesContainer)
        assert ServicesContainer._instance is instance

    def test_init_initializes_empty_container(self):
        """Test that __init__ creates an empty container"""
        container = ServicesContainer()

        assert container.pipefy_client is None

    @patch("pipefy_mcp.core.container.PipefyClient")
    def test_initialize_services_creates_pipefy_client(self, mock_pipefy_client_class):
        """Test that initialize_services creates and assigns PipefyClient"""
        mock_client = Mock(spec=PipefyClient)
        mock_pipefy_client_class.return_value = mock_client

        settings = Settings(
            pipefy=PipefySettings(
                graphql_url="https://api.pipefy.com/graphql",
                oauth_url="https://auth.pipefy.com/oauth/token",
                oauth_client="client_id",
                oauth_secret="client_secret",
            )
        )

        container = ServicesContainer()
        container.initialize_services(settings)

        mock_pipefy_client_class.assert_called_once_with(settings=settings.pipefy)
        assert container.pipefy_client is mock_client

    def test_shutdown_method_exists(self):
        """Test that shutdown method exists (currently a no-op)"""
        container = ServicesContainer()

        # Should not raise any exception
        container.shutdown()
