"""The engine/session split: shared endpoints, per-identity sessions."""

import pytest
from pipefy_auth import StaticBearerAuth

from pipefy_sdk import PipefyClient, PipefyEngine
from pipefy_sdk.settings import PipefySettings


@pytest.fixture
def settings() -> PipefySettings:
    return PipefySettings(base_url="https://api.pipefy.com")


@pytest.mark.unit
def test_build_needs_no_credential(settings):
    """The engine is auth-agnostic: it builds from settings alone, no auth."""
    engine = PipefyEngine.build(settings, surface="mcp")
    assert engine.settings is settings
    # The shared endpoints are built once and target each Pipefy endpoint URL.
    assert engine.endpoints.public._graphql_url == settings.graphql_url
    assert engine.endpoints.internal._graphql_url == settings.internal_api_url


@pytest.mark.unit
def test_session_binds_the_given_auth(settings):
    """A session is a PipefyClient whose executors carry the session's auth."""
    engine = PipefyEngine.build(settings)
    auth = StaticBearerAuth("session-token")

    client = engine.session(auth)

    assert isinstance(client, PipefyClient)
    assert client._pipe_service._executor.auth is auth
    assert client._internal_executor.auth is auth


@pytest.mark.unit
def test_two_sessions_share_endpoints_but_carry_distinct_auth(settings):
    """Different identities reuse one endpoint (one schema cache), different auth."""
    engine = PipefyEngine.build(settings)
    alice, bob = StaticBearerAuth("alice"), StaticBearerAuth("bob")

    a = engine.session(alice)
    b = engine.session(bob)

    # Same shared endpoint object backs both sessions' public executors.
    assert a._pipe_service._executor.endpoint is b._pipe_service._executor.endpoint
    # But each session binds its own identity.
    assert a._pipe_service._executor.auth is alice
    assert b._pipe_service._executor.auth is bob
