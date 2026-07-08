import time
from unittest.mock import patch

import httpx
import pytest
from _rs_fixtures import authenticated_user, remote_rs_settings, request_with_user
from pipefy_auth import (
    AuthSettings,
    RefreshableBearerAuth,
    StaticBearerAuth,
    TokenResponse,
)
from pipefy_auth.storage import StoredSession
from pipefy_sdk import PipefyClient, PipefySettings

from pipefy_mcp._docs import DOCS_SETUP_REF
from pipefy_mcp.core.runtime import (
    McpRuntime,
    RequestScopedIdentity,
    StartupIdentity,
)
from pipefy_mcp.settings import McpSettings, Settings


def _settings() -> Settings:
    return Settings(
        pipefy=PipefySettings(base_url="https://api.pipefy.com"),
        auth=AuthSettings(),
    )


def _bearer_of(client: PipefyClient) -> str:
    """The Authorization header the session's shared executor sends outbound."""
    auth = client._pipe_service._executor.auth
    request = httpx.Request("POST", "https://api.pipefy.test/graphql")
    return next(auth.auth_flow(request)).headers["Authorization"]


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
    """The runtime owns one auth-agnostic engine and opens a session per request.

    Construction resolves no credential; the credential (and its fail-fast) is
    resolved by the ``for_profile`` factory, see ``TestForProfile``.
    """

    @pytest.mark.unit
    def test_construction_needs_no_configured_credential(self, clear_auth_env):
        """Building the runtime resolves no credential: the engine is auth-agnostic.

        Both identity variants construct with empty ``AuthSettings`` and no network
        I/O; the credential is resolved at the composition root, not here.
        """
        McpRuntime(_settings(), RequestScopedIdentity())
        McpRuntime(_settings(), StartupIdentity(StaticBearerAuth("tok")))

    @pytest.mark.unit
    def test_startup_identity_session_binds_the_resolved_auth(self):
        """The stdio profile's one startup credential backs every session."""
        auth = StaticBearerAuth("startup-token")
        runtime = McpRuntime(_settings(), StartupIdentity(auth))

        client = runtime.session_for_request(None)

        assert client._pipe_service._executor.auth is auth
        assert _bearer_of(client) == "Bearer startup-token"

    @pytest.mark.unit
    def test_request_scoped_session_binds_the_requests_validated_bearer(self):
        """The hosted profile snapshots the request's validated bearer into the session."""
        runtime = McpRuntime(_settings(), RequestScopedIdentity())

        client = runtime.session_for_request(
            request_with_user(authenticated_user("caller-token"))
        )

        assert _bearer_of(client) == "Bearer caller-token"

    @pytest.mark.unit
    def test_sessions_isolate_concurrent_callers_bearers(self):
        """Two sessions under different request identities bind different bearers.

        The on-behalf-of acceptance criterion: one shared engine, a per-request
        session each, and no chance of one caller's bearer reaching another's calls.
        """
        runtime = McpRuntime(_settings(), RequestScopedIdentity())

        alice = runtime.session_for_request(
            request_with_user(authenticated_user("alice"))
        )
        bob = runtime.session_for_request(request_with_user(authenticated_user("bob")))

        assert _bearer_of(alice) == "Bearer alice"
        assert _bearer_of(bob) == "Bearer bob"
        # The isolated sessions still share one engine's endpoints (one schema cache).
        assert (
            alice._pipe_service._executor.endpoint
            is bob._pipe_service._executor.endpoint
        )


class TestForProfile:
    """``for_profile`` turns the resolved profile into wired inbound + outbound auth.

    The remote profile picks a per-request identity and builds the inbound
    resource-server pair (failing fast without one); every other profile resolves
    the one startup credential and fails fast when none is configured.
    """

    @pytest.mark.unit
    def test_remote_selects_request_scoped_identity_and_builds_inbound_auth(self):
        """Remote wires a per-request identity and an inbound RS pair, resolving no credential."""
        runtime = McpRuntime.for_profile(remote_rs_settings())

        assert runtime.inbound_auth is not None
        assert isinstance(runtime._identity, RequestScopedIdentity)

    @pytest.mark.unit
    def test_remote_snapshots_the_callers_bearer_into_its_session(self):
        """A session opened under the remote profile carries the request's validated bearer."""
        runtime = McpRuntime.for_profile(remote_rs_settings())

        client = runtime.session_for_request(
            request_with_user(authenticated_user("caller-token"))
        )

        assert _bearer_of(client) == "Bearer caller-token"

    @pytest.mark.unit
    def test_remote_without_resource_server_fails_fast(
        self, clear_auth_env, monkeypatch
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

    @pytest.mark.unit
    def test_local_static_token_binds_the_static_bearer(self, clear_auth_env):
        """``PIPEFY_TOKEN`` resolves to a static-bearer startup identity, no inbound auth."""
        settings = Settings(
            pipefy=PipefySettings(base_url="https://api.pipefy.com"),
            auth=AuthSettings(static_token="env-bearer"),
        )

        runtime = McpRuntime.for_profile(settings)

        assert runtime.inbound_auth is None
        assert _bearer_of(runtime.session_for_request(None)) == "Bearer env-bearer"

    @pytest.mark.unit
    @patch("pipefy_auth.resolver.load_session", lambda **_: None)
    def test_local_without_credential_fails_fast(self, clear_auth_env):
        """No PIPEFY_TOKEN and no service-account triple → raises when building."""
        settings = Settings(
            pipefy=PipefySettings(base_url="https://api.pipefy.com"),
            auth=AuthSettings(),
        )
        with pytest.raises(RuntimeError, match="Missing Pipefy authentication") as exc:
            McpRuntime.for_profile(settings)
        assert DOCS_SETUP_REF in str(exc.value)

    @pytest.mark.unit
    def test_local_stored_session_binds_a_refreshable_auth(self, clear_auth_env):
        """The stored-session arm wires a lazily-refreshing auth; no eager network I/O."""
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
        client = runtime.session_for_request(None)
        assert isinstance(client._pipe_service._executor.auth, RefreshableBearerAuth)
