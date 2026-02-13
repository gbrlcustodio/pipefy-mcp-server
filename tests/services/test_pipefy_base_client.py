import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql import Client
from gql.transport.exceptions import TransportAlreadyConnected

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.settings import PipefySettings


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


@pytest.mark.unit
def test_base_pipefy_client_raises_when_both_schema_and_client_provided():
    """Test that providing both schema and client raises ValueError."""
    mock_client = MagicMock(spec=Client)

    with pytest.raises(ValueError) as exc:
        BasePipefyClient(schema="some_schema", client=mock_client)

    assert "Cannot specify both 'schema' and 'client'" in str(exc.value)


@pytest.mark.unit
def test_init_raises_when_settings_is_none_and_no_client_provided():
    """Test that __init__ raises ValueError when settings is None and no client provided."""
    with pytest.raises(ValueError) as exc:
        BasePipefyClient(settings=None, client=None)

    assert "Settings must be provided to create a GraphQL client" in str(exc.value)


@pytest.mark.unit
def test_init_raises_when_graphql_url_is_none():
    """Test that __init__ raises ValueError when graphql_url is None."""
    settings = PipefySettings(
        graphql_url=None,
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )

    with pytest.raises(ValueError) as exc:
        BasePipefyClient(settings=settings)

    assert "GraphQL URL must be provided in settings" in str(exc.value)


@pytest.mark.unit
def test_init_raises_when_oauth_url_is_none():
    """Test that __init__ raises ValueError when oauth_url is None."""
    settings = PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url=None,
        oauth_client="client_id",
        oauth_secret="client_secret",
    )

    with pytest.raises(ValueError) as exc:
        BasePipefyClient(settings=settings)

    assert "OAuth URL must be provided in settings" in str(exc.value)


@pytest.mark.unit
def test_init_raises_when_oauth_client_is_none():
    """Test that __init__ raises ValueError when oauth_client is None."""
    settings = PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client=None,
        oauth_secret="client_secret",
    )

    with pytest.raises(ValueError) as exc:
        BasePipefyClient(settings=settings)

    assert "OAuth client ID must be provided in settings" in str(exc.value)


@pytest.mark.unit
def test_init_raises_when_oauth_secret_is_none():
    """Test that __init__ raises ValueError when oauth_secret is None."""
    settings = PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret=None,
    )

    with pytest.raises(ValueError) as exc:
        BasePipefyClient(settings=settings)

    assert "OAuth client secret must be provided in settings" in str(exc.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_concurrent_calls_do_not_raise_transport_already_connected():
    """Two concurrent execute_query calls must not raise Transport is already connected.

    When get_start_form_fields and get_pipe (or any two tools) are invoked in parallel
    by the MCP client, both use the same shared gql Client. The client's transport
    allows only one active session (connect) at a time; a second concurrent
    ``async with client`` triggers TransportAlreadyConnected. This test uses a
    mock client that reproduces that behavior and asserts that BasePipefyClient
    serializes access (e.g. with a lock) so both calls succeed.
    """
    query = object()
    variables = {"pipe_id": 123}
    result_payload = {"pipe": {}}

    connected = False

    async def aenter(self):
        nonlocal connected
        if connected:
            raise TransportAlreadyConnected("Transport is already connected")
        connected = True
        return mock_session

    async def aexit(self, *args):
        nonlocal connected
        connected = False
        return None

    mock_session = AsyncMock()

    async def execute_mock(*args, **kwargs):
        await asyncio.sleep(0)  # Yield so the second concurrent call can hit __aenter__
        return result_payload

    mock_session.execute = execute_mock

    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = aenter
    mock_client.__aexit__ = aexit

    base = BasePipefyClient(client=mock_client)

    results = await asyncio.gather(
        base.execute_query(query, variables),
        base.execute_query(query, variables),
    )

    assert results[0] == result_payload
    assert results[1] == result_payload
