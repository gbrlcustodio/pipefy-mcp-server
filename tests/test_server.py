from datetime import timedelta

import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.server import mcp as mcp_server
from pipefy_mcp.settings import settings


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


@pytest.mark.anyio
async def test_register_tools(client_session):
    # Skip if settings are not properly configured (e.g., no GraphQL URL)
    if not settings.pipefy.graphql_url:
        pytest.skip("GraphQL URL not configured for integration tests")

    expected_tool_names = [
        "add_card_comment",
        "create_card",
        "delete_card",
        "get_card",
        "get_cards",
        "get_pipe",
        "get_pipe_members",
        "get_start_form_fields",
        "move_card_to_phase",
        "search_pipes",
        "update_card",
        "update_card_field",
    ]

    async with client_session as session:
        result = await session.list_tools()
        actual_tool_names = [tool.name for tool in result.tools]

        assert sorted(expected_tool_names) == sorted(actual_tool_names), (
            "Expected create_card to be available"
        )
