import logging
import time
from unittest.mock import Mock, patch

import pytest
from pipefy_auth import (
    AuthSettings,
    RefreshableBearerAuth,
    RefreshError,
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
    """The stdio/local profile resolves one credential at startup."""

    @pytest.fixture(autouse=True)
    def clear_auth_env(self, monkeypatch):
        """Strip ambient ``PIPEFY_*`` auth env so ``AuthSettings()`` is hermetic."""
        for key in _AUTH_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)

    def test_init_leaves_the_client_unbuilt(self):
        """Construction is pure: no client until ``initialize`` runs."""
        runtime = McpRuntime(
            _settings(_service_account_auth_settings()), StartupIdentity()
        )

        assert runtime.pipefy_client is None

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    async def test_initialize_builds_the_pipefy_client(
        self,
        mock_pipefy_client_class,
    ):
        """``initialize`` builds and assigns the shared ``PipefyClient``."""
        mock_client = Mock(spec=PipefyClient)
        mock_pipefy_client_class.return_value = mock_client
        settings = _settings(_service_account_auth_settings())

        runtime = McpRuntime(settings, StartupIdentity())
        await runtime.initialize()

        mock_pipefy_client_class.assert_called_once()
        kwargs = mock_pipefy_client_class.call_args.kwargs
        assert kwargs["settings"] is settings.pipefy
        assert kwargs["surface"] == "mcp"
        assert "auth" in kwargs
        assert runtime.pipefy_client is mock_client

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    async def test_pipefy_token_wins_over_service_account(
        self,
        mock_pipefy_client_class,
    ):
        """``PIPEFY_TOKEN`` outranks ``PIPEFY_SERVICE_ACCOUNT_*`` (same precedence as the CLI)."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)
        settings = _settings(AuthSettings(static_token="env-bearer"))

        await McpRuntime(settings, StartupIdentity()).initialize()

        pc_auth = mock_pipefy_client_class.call_args.kwargs["auth"]
        assert isinstance(pc_auth, StaticBearerAuth)

    # Patch ``load_session``: ``auth_url``'s prod default makes the stored-session
    # tier always reachable, so a host with a real keychain entry would otherwise
    # satisfy resolution and break the assertion.
    @patch("pipefy_auth.resolver.load_session", lambda **_: None)
    @patch("pipefy_mcp.core.runtime.PipefyClient")
    async def test_raises_when_no_auth_source_configured(
        self,
        mock_pipefy_client_class,
    ):
        """No PIPEFY_TOKEN and no service-account triple → runtime error."""
        settings = _settings(AuthSettings())
        with pytest.raises(
            RuntimeError, match="Missing Pipefy authentication"
        ) as exc_info:
            await McpRuntime(settings, StartupIdentity()).initialize()
        assert DOCS_SETUP_REF in str(exc_info.value)

    @patch("pipefy_mcp.core.runtime.ensure_fresh_session")
    @patch("pipefy_mcp.core.runtime.PipefyClient")
    async def test_warms_up_stored_session(
        self,
        mock_pipefy_client_class,
        mock_ensure_fresh_session,
    ):
        """When the resolved method is the stored session, the refresh is pre-warmed."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)
        settings = _settings(_stored_session_auth_settings())
        with patch(
            "pipefy_auth.resolver.load_session",
            return_value=_fresh_stored_session(),
        ):
            await McpRuntime(settings, StartupIdentity()).initialize()

        pc_auth = mock_pipefy_client_class.call_args.kwargs["auth"]
        assert isinstance(pc_auth, RefreshableBearerAuth)
        mock_ensure_fresh_session.assert_called_once_with(
            issuer="https://signin.pipefy.com/realms/pipefy",
            client_id=settings.auth.auth_client_id,
        )

    @patch("pipefy_mcp.core.runtime.ensure_fresh_session")
    @patch("pipefy_mcp.core.runtime.PipefyClient")
    async def test_does_not_warm_up_when_static_token_wins(
        self,
        mock_pipefy_client_class,
        mock_ensure_fresh_session,
    ):
        """A configured ``PIPEFY_AUTH_URL`` is ignored at warm-up when a higher method wins."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)
        settings = _settings(
            AuthSettings(
                static_token="env-bearer",
                auth_url="https://signin.pipefy.com/realms/pipefy",
            )
        )
        # Force a detectable stored session so we prove precedence, not absence.
        with patch(
            "pipefy_auth.resolver.load_session",
            return_value=_fresh_stored_session(),
        ):
            await McpRuntime(settings, StartupIdentity()).initialize()

        mock_ensure_fresh_session.assert_not_called()

    @patch("pipefy_mcp.core.runtime.ensure_fresh_session")
    @patch("pipefy_mcp.core.runtime.PipefyClient")
    async def test_aborts_before_client_when_refresh_fails(
        self,
        mock_pipefy_client_class,
        mock_ensure_fresh_session,
        caplog,
    ):
        """A failed warm-up logs the ``pipefy auth login`` hint and surfaces ``RefreshError`` *before* ``PipefyClient`` is constructed."""
        mock_ensure_fresh_session.side_effect = RefreshError("invalid_grant")
        settings = _settings(_stored_session_auth_settings())
        with patch(
            "pipefy_auth.resolver.load_session",
            return_value=_fresh_stored_session(),
        ):
            with caplog.at_level(logging.ERROR, logger="pipefy_mcp.core.runtime"):
                with pytest.raises(RefreshError, match="invalid_grant"):
                    await McpRuntime(settings, StartupIdentity()).initialize()

        mock_pipefy_client_class.assert_not_called()
        hint_records = [
            r
            for r in caplog.records
            if r.name == "pipefy_mcp.core.runtime" and r.levelno == logging.ERROR
        ]
        assert len(hint_records) == 1
        hint_message = hint_records[0].getMessage()
        assert "invalid_grant" in hint_message
        assert "pipefy auth login" in hint_message
        assert DOCS_SETUP_REF in hint_message


class TestRequestScopedIdentity:
    """The hosted profile builds the shared client with no startup credential."""

    def _runtime(self) -> McpRuntime:
        return McpRuntime(
            _settings(AuthSettings()),
            RequestScopedIdentity(RequestContextBearerAuth()),
        )

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    async def test_builds_client_with_the_request_scoped_auth_and_no_resolution(
        self,
        mock_pipefy_client_class,
    ):
        """No credential is resolved; the client carries the request-scoped adapter."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)

        def _poison(**_kwargs):
            raise AssertionError(
                "resolve_pipefy_auth must not run for the hosted profile"
            )

        with patch("pipefy_mcp.core.runtime.resolve_pipefy_auth", _poison):
            await self._runtime().initialize()

        auth = mock_pipefy_client_class.call_args.kwargs["auth"]
        assert isinstance(auth, RequestContextBearerAuth)

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    async def test_needs_no_configured_credential(
        self,
        mock_pipefy_client_class,
        monkeypatch,
    ):
        """Booting the hosted profile with no PIPEFY_* auth does not raise."""
        for key in _AUTH_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)

        await self._runtime().initialize()  # would raise on a missing-auth path

        mock_pipefy_client_class.assert_called_once()


class TestInitializeIsIdempotent:
    """The client is built once and shared across repeated initialize calls."""

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    async def test_second_initialize_is_a_no_op(self, mock_pipefy_client_class):
        """Streamable HTTP re-enters the lifespan per session; the client builds once."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)
        runtime = McpRuntime(
            _settings(AuthSettings()),
            RequestScopedIdentity(RequestContextBearerAuth()),
        )

        await runtime.initialize()
        first = runtime.pipefy_client
        await runtime.initialize()

        mock_pipefy_client_class.assert_called_once()
        assert runtime.pipefy_client is first
