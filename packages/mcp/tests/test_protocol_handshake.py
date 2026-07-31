"""What the Pipefy MCP server negotiates, and what identity it advertises.

Both facts were previously unasserted anywhere in the suite: ``protocolVersion``
only ever appeared as a request input, and ``serverInfo`` not at all. The gap is
not theoretical. The tool tests reach the server through ``_mcp_compat``, which
pins ``mode="legacy"``; drop that pin and the only failures are seven
elicitation tests in ``tools/test_pipe_tools.py``, which read as an elicitation
bug rather than as "the negotiated revision moved to one with no back channel".
These tests put the revision and the identity under direct assertion so that
signal arrives here first.

Each expected literal is also tied to the SDK's version registry, so a test
failure separates the two causes it can have: the revision this deployment
negotiates changed (the literal), or the SDK's revision set changed underneath
it (the registry assertion).
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from _mcp_compat import (
    create_connected_server_and_client_session as create_client_session,
)
from mcp.client import Client
from mcp_types.version import LATEST_HANDSHAKE_VERSION, LATEST_MODERN_VERSION
from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings

from pipefy_mcp import __version__ as pipefy_mcp_version
from pipefy_mcp.server import build_pipefy_mcp_server
from pipefy_mcp.settings import Settings

SERVED_PROTOCOL_VERSION = "2025-11-25"
"""The revision a client reaches this server on today: the newest one available
through the ``initialize`` handshake."""

MODERN_PROTOCOL_VERSION = "2026-07-28"
"""The revision a default (``mode="auto"``) client negotiates instead. It has no
server-to-client back channel, so ``ctx.elicit`` cannot be used on it."""

_LOCAL_SETTINGS = Settings(
    pipefy=PipefySettings(base_url="https://api.pipefy.com"),
    auth=AuthSettings(),
)


@pytest.fixture
def mocked_runtime():
    """Patch the runtime factory so building resolves no real credential."""
    runtime = MagicMock()
    runtime.session_for_request.return_value = MagicMock()
    runtime.inbound_auth = None
    with patch("pipefy_mcp.server.McpRuntime.for_profile", return_value=runtime):
        yield runtime


@pytest.mark.unit
def test_expected_revisions_match_the_sdk_registry():
    """Guard the literals below against an SDK that moved its revision set.

    Without this, bumping ``mcp`` to a release that adds a handshake revision (or
    a newer modern one) would fail the negotiation tests with no indication that
    the SDK, not this server, is what changed.
    """
    assert LATEST_HANDSHAKE_VERSION == SERVED_PROTOCOL_VERSION
    assert LATEST_MODERN_VERSION == MODERN_PROTOCOL_VERSION


@pytest.mark.anyio
async def test_handshake_client_negotiates_the_served_revision(mocked_runtime):
    app = build_pipefy_mcp_server(_LOCAL_SETTINGS)
    session = create_client_session(
        app,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )
    async with session as client:
        assert client.protocol_version == SERVED_PROTOCOL_VERSION


@pytest.mark.anyio
async def test_default_client_negotiates_the_modern_revision(mocked_runtime):
    """A ``Client`` with no ``mode`` discovers instead of handshaking.

    This is the behaviour ``_mcp_compat``'s ``mode="legacy"`` pin exists to
    avoid, asserted rather than left implicit. Elicitation is unavailable on
    this revision (no back channel), which is why the tool tests pin.
    """
    app = build_pipefy_mcp_server(_LOCAL_SETTINGS)
    async with Client(app, raise_exceptions=True) as client:
        assert client.protocol_version == MODERN_PROTOCOL_VERSION


@pytest.mark.anyio
async def test_server_advertises_its_name_and_package_version(mocked_runtime):
    """``serverInfo`` carries the identity clients log and gate features on."""
    app = build_pipefy_mcp_server(_LOCAL_SETTINGS)
    session = create_client_session(
        app,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )
    async with session as client:
        server_info = client.server_info

    assert server_info is not None
    assert server_info.name == "pipefy"
    assert server_info.version == pipefy_mcp_version
    # An unversioned SDK server reports an empty string rather than substituting
    # its own version, so an empty value here means the version never arrived.
    assert server_info.version != ""


@pytest.mark.anyio
async def test_modern_client_receives_the_same_server_identity(mocked_runtime):
    """The identity is revision-independent: it rides the discover result too."""
    app = build_pipefy_mcp_server(_LOCAL_SETTINGS)
    async with Client(app, raise_exceptions=True) as client:
        server_info = client.server_info

    assert server_info is not None
    assert server_info.name == "pipefy"
    assert server_info.version == pipefy_mcp_version
