import logging
import time
from unittest.mock import Mock, patch

import pytest
from pipefy_auth import (
    DEFAULT_AUTH_CLIENT_ID,
    CredentialSources,
    OidcClient,
    RefreshableBearerAuth,
    RefreshError,
    ServiceAccount,
    StaticBearerAuth,
    TokenResponse,
)
from pipefy_auth.storage import StoredSession
from pipefy_infra.deployment import DeploymentConfig
from pipefy_sdk import PipefyClient, PipefyEndpoints

from pipefy_mcp._docs import DOCS_SETUP_REF
from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.runtime import McpRuntime, McpSettings, ResourceServerIdentity

_AUTH_ENV_KEYS = (
    "PIPEFY_TOKEN",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET",
    "PIPEFY_OAUTH_CLIENT",
    "PIPEFY_OAUTH_SECRET",
    "PIPEFY_AUTH_ISSUER_URL",
    "PIPEFY_BASE_URL",
    "PIPEFY_AUTH_DISABLE_STORED_SESSION",
    "PIPEFY_AUTH_KEYCHAIN_BACKEND",
)

# One deployment, the source of the parsed endpoints the runtime carries.
_DEPLOYMENT = DeploymentConfig(base_url="https://api.pipefy.com")
_ENDPOINTS = PipefyEndpoints(
    graphql_url=_DEPLOYMENT.graphql_url,
    interfaces_graphql_url=_DEPLOYMENT.interfaces_graphql_url,
    internal_api_url=_DEPLOYMENT.internal_api_url,
)
_ISSUER = "https://signin.pipefy.com/realms/pipefy"


def _runtime(credentials: CredentialSources) -> McpRuntime:
    """Build a complete MCP ``McpRuntime`` around the given parsed credentials."""
    return McpRuntime(
        endpoints=_ENDPOINTS,
        allow_insecure_urls=False,
        reuse_schema=False,
        default_webhook_name="Pipefy Webhook",
        credentials=credentials,
        keychain_backend="auto",
        mcp=McpSettings(),
        jwt=None,
        resource_server=ResourceServerIdentity(),
    )


def _service_account_credentials() -> CredentialSources:
    return CredentialSources(
        service_account=ServiceAccount(
            token_url=_DEPLOYMENT.oauth_token_url,
            client_id="client_id",
            client_secret="client_secret",
        )
    )


def _stored_session_credentials() -> CredentialSources:
    return CredentialSources(
        oidc_client=OidcClient(issuer_url=_ISSUER, client_id=DEFAULT_AUTH_CLIENT_ID)
    )


def _fresh_stored_session() -> StoredSession:
    return StoredSession(
        issuer="https://signin.pipefy.com/realms/pipefy",
        client_id="pipefy-cli",
        obtained_at=int(time.time()),
        token=TokenResponse(
            access_token="ACCESS",
            refresh_token="REFRESH",
            expires_in=3600,
        ),
    )


class TestServicesContainer:
    """Test cases for ServicesContainer"""

    @pytest.fixture(autouse=True)
    def clear_auth_env(self, monkeypatch):
        """Strip ambient ``PIPEFY_*`` auth env so the readers are hermetic."""
        for key in _AUTH_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)

    def test_init_initializes_empty_container(self):
        """Test that __init__ creates an empty container"""
        container = ServicesContainer()

        assert container.pipefy_client is None

    @patch("pipefy_mcp.core.container.PipefyClient")
    async def test_initialize_services_creates_pipefy_client(
        self,
        mock_pipefy_client_class,
    ):
        """Test that initialize_services creates and assigns PipefyClient"""
        mock_client = Mock(spec=PipefyClient)
        mock_client.client = Mock()
        mock_pipefy_client_class.return_value = mock_client

        runtime = _runtime(_service_account_credentials())

        container = ServicesContainer()
        await container.initialize_services(runtime)

        mock_pipefy_client_class.assert_called_once()
        kwargs = mock_pipefy_client_class.call_args.kwargs
        endpoints = mock_pipefy_client_class.call_args.args[0]
        assert isinstance(endpoints, PipefyEndpoints)
        assert endpoints.graphql_url == runtime.endpoints.graphql_url
        assert "auth" in kwargs
        assert container.pipefy_client is mock_client

    @patch("pipefy_mcp.core.container.PipefyClient")
    async def test_initialize_services_picks_up_pipefy_token_over_service_account(
        self,
        mock_pipefy_client_class,
    ):
        """``PIPEFY_TOKEN`` outranks ``PIPEFY_SERVICE_ACCOUNT_*`` (same precedence as the CLI)."""
        mock_client = Mock(spec=PipefyClient)
        mock_client.client = Mock()
        mock_pipefy_client_class.return_value = mock_client
        runtime = _runtime(CredentialSources(static_token="env-bearer"))
        await ServicesContainer().initialize_services(runtime)
        pc_auth = mock_pipefy_client_class.call_args.kwargs["auth"]
        assert isinstance(pc_auth, StaticBearerAuth)

    # Patch ``load_session``: ``issuer_url``'s prod default makes the stored-session
    # tier always reachable, so a host with a real keychain entry would otherwise
    # satisfy resolution and break the assertion.
    @patch("pipefy_auth.resolver.load_session", lambda **_: None)
    @patch("pipefy_mcp.core.container.PipefyClient")
    async def test_initialize_services_raises_when_no_auth_source_configured(
        self,
        mock_pipefy_client_class,
    ):
        """No PIPEFY_TOKEN and no service-account pair -> runtime error."""
        runtime = _runtime(CredentialSources())
        with pytest.raises(
            RuntimeError, match="Missing Pipefy authentication"
        ) as exc_info:
            await ServicesContainer().initialize_services(runtime)
        assert DOCS_SETUP_REF in str(exc_info.value)

    @patch("pipefy_mcp.core.container.ensure_fresh_session")
    @patch("pipefy_mcp.core.container.PipefyClient")
    async def test_initialize_services_warms_up_stored_session(
        self,
        mock_pipefy_client_class,
        mock_ensure_fresh_session,
    ):
        """When the resolved tier is the stored session, the refresh is pre-warmed."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)
        runtime = _runtime(_stored_session_credentials())
        with patch(
            "pipefy_auth.resolver.load_session",
            return_value=_fresh_stored_session(),
        ):
            await ServicesContainer().initialize_services(runtime)

        pc_auth = mock_pipefy_client_class.call_args.kwargs["auth"]
        assert isinstance(pc_auth, RefreshableBearerAuth)
        mock_ensure_fresh_session.assert_called_once_with(
            issuer="https://signin.pipefy.com/realms/pipefy",
            client_id=DEFAULT_AUTH_CLIENT_ID,
        )

    @patch("pipefy_mcp.core.container.ensure_fresh_session")
    @patch("pipefy_mcp.core.container.PipefyClient")
    async def test_initialize_services_does_not_warm_up_when_static_token_wins(
        self,
        mock_pipefy_client_class,
        mock_ensure_fresh_session,
    ):
        """A configured ``PIPEFY_AUTH_ISSUER_URL`` is ignored at warm-up when a higher tier wins."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)
        runtime = _runtime(
            CredentialSources(
                static_token="env-bearer",
                oidc_client=OidcClient(
                    issuer_url=_ISSUER, client_id=DEFAULT_AUTH_CLIENT_ID
                ),
            )
        )
        # Force a detectable stored session so we prove precedence, not absence.
        with patch(
            "pipefy_auth.resolver.load_session",
            return_value=_fresh_stored_session(),
        ):
            await ServicesContainer().initialize_services(runtime)

        mock_ensure_fresh_session.assert_not_called()

    @patch("pipefy_mcp.core.container.ensure_fresh_session")
    @patch("pipefy_mcp.core.container.PipefyClient")
    async def test_initialize_services_aborts_before_client_when_refresh_fails(
        self,
        mock_pipefy_client_class,
        mock_ensure_fresh_session,
        caplog,
    ):
        """A failed warm-up logs the ``pipefy auth login`` hint and surfaces ``RefreshError`` *before* ``PipefyClient`` is constructed."""
        mock_ensure_fresh_session.side_effect = RefreshError("invalid_grant")
        runtime = _runtime(_stored_session_credentials())
        with patch(
            "pipefy_auth.resolver.load_session",
            return_value=_fresh_stored_session(),
        ):
            with caplog.at_level(logging.ERROR, logger="pipefy_mcp.core.container"):
                with pytest.raises(RefreshError, match="invalid_grant"):
                    await ServicesContainer().initialize_services(runtime)

        mock_pipefy_client_class.assert_not_called()
        hint_records = [
            r
            for r in caplog.records
            if r.name == "pipefy_mcp.core.container" and r.levelno == logging.ERROR
        ]
        assert len(hint_records) == 1
        hint_message = hint_records[0].getMessage()
        assert "invalid_grant" in hint_message
        assert "pipefy auth login" in hint_message
        assert DOCS_SETUP_REF in hint_message
