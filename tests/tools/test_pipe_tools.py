from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp import ClientSession
from mcp.shared.context import RequestContext
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)
from mcp.types import (
    ElicitRequestParams,
    ElicitResult,
)

from pipefy_mcp.server import mcp as mcp_server


@pytest.fixture
def anyio_backend():
    return "anyio"


@pytest.fixture
def mock_pipefy_client():
    client = MagicMock()
    client.get_start_form_fields = AsyncMock(return_value={"start_form_fields": []})
    client.create_card = AsyncMock(return_value={"card": {"id": "789"}})
    return client


@pytest.fixture(autouse=True)
def mock_services_container(mocker, mock_pipefy_client):
    mocker.patch(
        "pipefy_mcp.core.container.ServicesContainer.get_instance"
    ).return_value.pipefy_client = mock_pipefy_client


async def elicitation_callback(
    context: RequestContext[ClientSession, Any],
    params: ElicitRequestParams,
) -> ElicitResult:
    return ElicitResult(action="accept", content={"confirm": True})


@pytest.fixture
def client_session(request) -> ClientSession:
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=request.param,
    )


@pytest.fixture
def pipe_id() -> int:
    return 12345


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [elicitation_callback], indirect=True)
async def test_create_card_tool_with_elicitation(client_session, pipe_id):
    async with client_session as session:
        result = await session.call_tool("create_card", {"pipe_id": pipe_id})
        assert result.isError is False, "Unexpected tool result"


@pytest.mark.anyio
@pytest.mark.parametrize("client_session", [None], indirect=True)
async def test_create_card_tool_without_elicitation(client_session, pipe_id):
    async with client_session as session:
        result = await session.call_tool(
            "create_card",
            {
                "pipe_id": pipe_id,
                "fields": {"field_1": "value_1", "field_2": "value_2"},
            },
        )
        assert result.isError is False, "Unexpected tool result"
