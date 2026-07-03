import time
from unittest.mock import Mock, patch

import pytest
from pipefy_auth import (
    AuthSettings,
    JwtValidationSettings,
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
from pipefy_mcp.settings import McpSettings, ResourceServerSettings, Settings

_RS_ISSUER = "https://idp.example.com/realms/x"
_RS_RESOURCE = "https://mcp.example.com/mcp"


def _settings() -> Settings:
    return Settings(
        pipefy=PipefySettings(base_url="https://api.pipefy.com"),
        auth=AuthSettings(),
    )


def _remote_rs_settings() -> Settings:
    """Remote profile with a fully-configured resource server (no network at build)."""
    return Settings(
        pipefy=PipefySettings(base_url="https://api.pipefy.com"),
        auth=AuthSettings(),
        mcp=McpSettings(profile="remote"),
        rs=ResourceServerSettings(resource_server_url=_RS_RESOURCE),
        jwt=JwtValidationSettings(issuer_url=_RS_ISSUER, jwks_uri=f"{_RS_ISSUER}/jwks"),
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


class TestMcpRuntime:
    """The runtime wires one shared client to the identity's auth, resolving nothing.

    The credential (and its fail-fast) is resolved by the ``for_profile`` factory,
    not by ``__init__``; see ``TestForProfile``.
    """

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_construction_wires_the_client_to_the_startup_auth(
        self, mock_pipefy_client_class
    ):
        """The stdio profile's one resolved credential backs the shared client."""
        mock_client = Mock(spec=PipefyClient)
        mock_pipefy_client_class.return_value = mock_client
        settings = _settings()
        auth = StaticBearerAuth("startup-token")

        runtime = McpRuntime(settings, StartupIdentity(auth))

        mock_pipefy_client_class.assert_called_once()
        kwargs = mock_pipefy_client_class.call_args.kwargs
        assert kwargs["settings"] is settings.pipefy
        assert kwargs["auth"] is auth
        assert kwargs["surface"] == "mcp"
        assert runtime.pipefy_client is mock_client
        assert runtime.inbound_auth is None

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_construction_wires_the_client_to_the_request_scoped_auth(
        self, mock_pipefy_client_class
    ):
        """The hosted profile's client carries the request-context bearer adapter."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)
        auth = RequestContextBearerAuth()

        McpRuntime(_settings(), RequestScopedIdentity(auth))

        assert mock_pipefy_client_class.call_args.kwargs["auth"] is auth

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_construction_resolves_no_credential(
        self, mock_pipefy_client_class, clear_auth_env
    ):
        """Building the runtime never resolves a credential; that is the factory's job.

        Both identity variants construct with empty ``AuthSettings`` and no
        keychain read, so a poisoned ``resolve_pipefy_auth`` proves neither arm
        touches it.
        """
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)

        def _poison(**_kwargs):
            raise AssertionError("the runtime must not resolve a startup credential")

        with patch("pipefy_mcp.core.runtime.resolve_pipefy_auth", _poison):
            McpRuntime(_settings(), StartupIdentity(StaticBearerAuth("tok")))
            McpRuntime(_settings(), RequestScopedIdentity(RequestContextBearerAuth()))


class TestForProfile:
    """``for_profile`` turns the resolved profile into wired inbound + outbound auth.

    The remote profile picks a per-request identity and builds the inbound
    resource-server pair (failing fast without one); every other profile resolves
    the one startup credential and fails fast when none is configured.
    """

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_remote_selects_request_scoped_identity_and_builds_inbound_auth(
        self, mock_pipefy_client_class
    ):
        """Remote wires a per-request bearer and an inbound RS pair, resolving no credential."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)

        def _poison(**_kwargs):
            raise AssertionError("remote must not resolve a startup credential")

        with patch("pipefy_mcp.core.runtime.resolve_pipefy_auth", _poison):
            runtime = McpRuntime.for_profile(_remote_rs_settings())

        assert runtime.inbound_auth is not None
        assert isinstance(
            mock_pipefy_client_class.call_args.kwargs["auth"], RequestContextBearerAuth
        )

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_remote_without_resource_server_fails_fast(
        self, mock_pipefy_client_class, clear_auth_env, monkeypatch
    ):
        """Remote with no RESOURCE_SERVER_URL refuses to build the runtime."""
        monkeypatch.delenv("PIPEFY_MCP_RS_RESOURCE_SERVER_URL", raising=False)
        settings = Settings(
            pipefy=PipefySettings(base_url="https://api.pipefy.com"),
            auth=AuthSettings(),
            mcp=McpSettings(profile="remote"),
        )
        with pytest.raises(RuntimeError, match="requires a resource server"):
            McpRuntime.for_profile(settings)

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_local_static_token_becomes_a_startup_identity(
        self, mock_pipefy_client_class, clear_auth_env
    ):
        """``PIPEFY_TOKEN`` resolves to a static-bearer startup identity, no inbound auth."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)
        settings = Settings(
            pipefy=PipefySettings(base_url="https://api.pipefy.com"),
            auth=AuthSettings(static_token="env-bearer"),
        )

        runtime = McpRuntime.for_profile(settings)

        assert runtime.inbound_auth is None
        assert isinstance(
            mock_pipefy_client_class.call_args.kwargs["auth"], StaticBearerAuth
        )

    # Patch ``load_session``: ``auth_url``'s prod default makes the stored-session
    # tier reachable, so a host with a real keychain entry would otherwise satisfy
    # resolution and break the assertion.
    @patch("pipefy_mcp.core.runtime.PipefyClient")
    @patch("pipefy_auth.resolver.load_session", lambda **_: None)
    def test_local_without_credential_fails_fast(
        self, mock_pipefy_client_class, clear_auth_env
    ):
        """No PIPEFY_TOKEN and no service-account triple → raises when building."""
        settings = Settings(
            pipefy=PipefySettings(base_url="https://api.pipefy.com"),
            auth=AuthSettings(),
        )
        with pytest.raises(RuntimeError, match="Missing Pipefy authentication") as exc:
            McpRuntime.for_profile(settings)
        assert DOCS_SETUP_REF in str(exc.value)

    @patch("pipefy_mcp.core.runtime.PipefyClient")
    def test_local_stored_session_builds_a_refreshable_startup_identity(
        self, mock_pipefy_client_class, clear_auth_env
    ):
        """The stored-session arm wires a lazily-refreshing auth; no eager network I/O."""
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)
        settings = Settings(
            pipefy=PipefySettings(base_url="https://api.pipefy.com"),
            auth=AuthSettings(auth_url="https://signin.pipefy.com/realms/pipefy"),
        )
        with patch(
            "pipefy_auth.resolver.load_session",
            return_value=_fresh_stored_session(),
        ):
            runtime = McpRuntime.for_profile(settings)

        assert runtime.inbound_auth is None
        assert isinstance(
            mock_pipefy_client_class.call_args.kwargs["auth"], RefreshableBearerAuth
        )
