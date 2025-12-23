from unittest.mock import AsyncMock, MagicMock

import pytest
from gql import Client

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_uses_injected_client_and_passthrough_variables():
    """Test execute_query uses the injected client and passes variable_values unchanged."""
    query = object()
    variables = {"a": 1, "nested": {"b": 2}}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"ok": True})

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    base = BasePipefyClient(client=mock_client)
    result = await base.execute_query(query, variables)

    mock_session.execute.assert_called_once_with(query, variable_values=variables)
    assert result == {"ok": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_bubbles_up_execute_errors_unchanged():
    """Test execute_query does not wrap exceptions raised by the GraphQL session."""
    query = object()
    variables = {"x": 1}
    expected_error = RuntimeError("boom")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=expected_error)

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    base = BasePipefyClient(client=mock_client)

    with pytest.raises(RuntimeError) as exc:
        await base.execute_query(query, variables)

    assert exc.value is expected_error


