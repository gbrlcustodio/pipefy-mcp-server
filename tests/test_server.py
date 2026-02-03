from datetime import timedelta
from unittest.mock import patch

import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.server import mcp as mcp_server
from pipefy_mcp.settings import PipefySettings, Settings


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def client_session():
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


# Minimal settings so server lifespan can start without real env (test only lists tools).
_MINIMAL_PIPEFY_SETTINGS = Settings(
    pipefy=PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://api.pipefy.com/oauth/token",
        oauth_client="test-client",
        oauth_secret="test-secret",
    )
)


@pytest.mark.anyio
async def test_register_tools(client_session):
    expected_tool_names = [
        "add_card_comment",
        "create_card",
        "delete_card",
        "fill_card_phase_fields",
        "get_card",
        "get_cards",
        "get_phase_fields",
        "get_pipe",
        "get_pipe_members",
        "get_start_form_fields",
        "move_card_to_phase",
        "search_pipes",
        "update_card",
        "update_card_field",
    ]

    with patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS):
        async with client_session as session:
            result = await session.list_tools()
            actual_tool_names = [tool.name for tool in result.tools]

            assert sorted(expected_tool_names) == sorted(actual_tool_names), (
                "Expected create_card to be available"
            )
