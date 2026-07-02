import time
from unittest.mock import Mock, patch

import pytest
from pipefy_auth import (
    AuthSettings,
    RefreshableBearerAuth,
    StaticBearerAuth,
    TokenResponse,
)
from pipefy_auth.storage import StoredSession
from pipefy_sdk import PipefyClient, PipefySettings

from pipefy_mcp._docs import DOCS_SETUP_REF
from pipefy_mcp.auth import RequestContextBearerAuth
from pipefy_mcp.core.runtime import (
    McpRuntime,
    RequestScopedIdentity,
    StartupIdentity,
)
from pipefy_mcp.settings import Settings

_AUTH_ENV_KEYS = (
    "PIPEFY_TOKEN",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET",
    "PIPEFY_OAUTH_CLIENT",
    "PIPEFY_OAUTH_SECRET",
    "PIPEFY_AUTH_URL",
    "PIPEFY_BASE_URL",
    "PIPEFY_DISABLE_STORED_SESSION",
    "PIPEFY_KEYCHAIN_BACKEND",
)


def _service_account_auth_settings() -> AuthSettings:
    return AuthSettings(
        service_account_client_id="client_id",
        service_account_client_secret="client_secret",
    )


def _stored_session_auth_settings() -> AuthSettings:
    return AuthSettings(auth_url="https://signin.pipefy.com/realms/pipefy")


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


def _settings(auth: AuthSettings) -> Settings:
    return Settings(
        pipefy=PipefySettings(base_url="https://api.pipefy.com"),
        auth=auth,
    )


class TestStartupIdentity:
    """The stdio/local profile resolves one credential when the runtime is built."""

    @pytest.fixture(autouse=True)
    def clear_auth_env(self, monkeypatch):
        """Strip ambient ``PIPEFY_*`` auth env so ``AuthSettings()`` is hermetic."""
        for key in _AUTH_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_construction_builds_the_pipefy_client(self, mock_pipefy_client_class):
        """Constructing the runtime builds and holds the shared ``PipefyClient``."""
        mock_client = Mock(spec=PipefyClient)
        mock_pipefy_client_class.return_value = mock_client
        settings = _settings(_service_account_auth_settings())

        runtime = McpRuntime(settings, StartupIdentity())

        mock_pipefy_client_class.assert_called_once()
        kwargs = mock_pipefy_client_class.call_args.kwargs
        assert kwargs["settings"] is settings.pipefy
        assert kwargs["surface"] == "mcp"
        assert "auth" in kwargs
        assert runtime.pipefy_client is mock_client

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_pipefy_token_wins_over_service_account(self, mock_pipefy_client_class):
        """``PIPEFY_TOKEN`` outranks ``PIPEFY_SERVICE_ACCOUNT_*`` (same precedence as the CLI)."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)
        settings = _settings(AuthSettings(static_token="env-bearer"))

        McpRuntime(settings, StartupIdentity())

        pc_auth = mock_pipefy_client_class.call_args.kwargs["auth"]
        assert isinstance(pc_auth, StaticBearerAuth)

    # Patch ``load_session``: ``auth_url``'s prod default makes the stored-session
    # tier always reachable, so a host with a real keychain entry would otherwise
    # satisfy resolution and break the assertion.
    @patch("pipefy_auth.resolver.load_session", lambda **_: None)
    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_raises_when_no_auth_source_configured(self, mock_pipefy_client_class):
        """No PIPEFY_TOKEN and no service-account triple → fails fast at construction."""
        settings = _settings(AuthSettings())
        with pytest.raises(
            RuntimeError, match="Missing Pipefy authentication"
        ) as exc_info:
            McpRuntime(settings, StartupIdentity())
        assert DOCS_SETUP_REF in str(exc_info.value)

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_stored_session_builds_refreshable_auth_without_network(
        self, mock_pipefy_client_class
    ):
        """The stored-session arm wires a lazily-refreshing auth; no eager network I/O.

        The refresh happens on the first request that needs a token, so building
        the client does no network call at startup.
        """
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)
        settings = _settings(_stored_session_auth_settings())
        with patch(
            "pipefy_auth.resolver.load_session",
            return_value=_fresh_stored_session(),
        ):
            McpRuntime(settings, StartupIdentity())

        pc_auth = mock_pipefy_client_class.call_args.kwargs["auth"]
        assert isinstance(pc_auth, RefreshableBearerAuth)


class TestRequestScopedIdentity:
    """The hosted profile builds the shared client with no startup credential."""

    def _runtime(self) -> McpRuntime:
        return McpRuntime(
            _settings(AuthSettings()),
            RequestScopedIdentity(RequestContextBearerAuth()),
        )

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_builds_client_with_the_request_scoped_auth_and_no_resolution(
        self, mock_pipefy_client_class
    ):
        """No credential is resolved; the client carries the request-scoped adapter."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)

        def _poison(**_kwargs):
            raise AssertionError(
                "resolve_pipefy_auth must not run for the hosted profile"
            )

        with patch("pipefy_mcp.core.runtime.resolve_pipefy_auth", _poison):
            self._runtime()

        auth = mock_pipefy_client_class.call_args.kwargs["auth"]
        assert isinstance(auth, RequestContextBearerAuth)

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_needs_no_configured_credential(
        self, mock_pipefy_client_class, monkeypatch
    ):
        """Booting the hosted profile with no PIPEFY_* auth does not raise."""
        for key in _AUTH_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)

        self._runtime()  # would raise on a missing-auth path

        mock_pipefy_client_class.assert_called_once()
