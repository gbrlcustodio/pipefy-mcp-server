from unittest.mock import Mock, patch

from pipefy_auth import AuthSettings, StaticBearerAuth
from pipefy_sdk import PipefyClient, PipefySettings

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


def _settings() -> Settings:
    return Settings(
        pipefy=PipefySettings(base_url="https://api.pipefy.com"),
        auth=AuthSettings(),
    )


class TestMcpRuntime:
    """The runtime wires one shared client to the identity's auth, resolving nothing.

    The credential (and its fail-fast) is resolved at the composition root, not
    here; see ``TestSelectAuthSource`` in ``tests/test_server.py``.
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
        self, mock_pipefy_client_class, monkeypatch
    ):
        """Building the runtime never resolves a credential; that is the root's job.

        Both identity variants construct with empty ``AuthSettings`` and no
        keychain read, so a poisoned ``resolve_pipefy_auth`` proves neither arm
        touches it.
        """
        for key in _AUTH_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        mock_pipefy_client_class.return_value = Mock(spec=PipefyClient)

        def _poison(**_kwargs):
            raise AssertionError("the runtime must not resolve a startup credential")

        with patch("pipefy_mcp.core.runtime.resolve_pipefy_auth", _poison):
            McpRuntime(_settings(), StartupIdentity(StaticBearerAuth("tok")))
            McpRuntime(_settings(), RequestScopedIdentity(RequestContextBearerAuth()))
