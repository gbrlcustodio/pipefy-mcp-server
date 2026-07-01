from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from gql import gql
from gql.graphql_request import GraphQLRequest
from gql.transport.httpx import HTTPXAsyncTransport
from graphql import ExecutionResult, GraphQLError
from pipefy_auth import StaticBearerAuth

from pipefy_sdk import __version__
from pipefy_sdk.graphql_executor import HttpxGraphQLExecutor
from pipefy_sdk.telemetry import telemetry_headers

GRAPHQL_URL = "https://api.pipefy.com/graphql"


def _bearer() -> StaticBearerAuth:
    return StaticBearerAuth("test-token")


def _sample_query() -> GraphQLRequest:
    return gql("{ __typename }")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_builds_transport_with_tls_verification():
    """HTTPXAsyncTransport must explicitly enable TLS certificate verification."""
    query = _sample_query()
    variables: dict = {}
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"ok": True})

    with (
        patch("pipefy_sdk.graphql_executor.HTTPXAsyncTransport") as mock_transport_cls,
        patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls,
    ):
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        base = HttpxGraphQLExecutor(url=GRAPHQL_URL, auth=_bearer())
        await base.execute_query(query, variables)

    mock_transport_cls.assert_called_once()
    assert mock_transport_cls.call_args.kwargs["verify"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_passes_variables_to_session():
    """Test execute_query creates a session and passes variable_values unchanged."""
    query = _sample_query()
    variables = {"a": 1, "nested": {"b": 2}}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"ok": True})

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        base = HttpxGraphQLExecutor(url=GRAPHQL_URL, auth=_bearer())
        result = await base.execute_query(query, variables)

    mock_session.execute.assert_called_once()
    request = mock_session.execute.call_args[0][0]
    assert isinstance(request, GraphQLRequest)
    assert request.variable_values == variables
    assert result == {"ok": True}
    assert mock_client_cls.call_args.kwargs["fetch_schema_from_transport"] is False
    assert "schema" not in mock_client_cls.call_args.kwargs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_omits_variable_values_for_empty_dict():
    """Empty variables omits variable_values on the bound GraphQLRequest."""
    query = _sample_query()
    variables: dict = {}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"ok": True})

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        base = HttpxGraphQLExecutor(url=GRAPHQL_URL, auth=_bearer())
        await base.execute_query(query, variables)

    request = mock_session.execute.call_args[0][0]
    assert isinstance(request, GraphQLRequest)
    assert request.variable_values is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_reuse_fetches_once_then_passes_cached_schema():
    """With cache_schema, first Client run introspects; next reuses schema."""
    query = _sample_query()
    variables: dict = {}
    cached_schema = object()
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[{"one": 1}, {"two": 2}])

    def _make_context_client():
        inst = MagicMock()
        inst.__aenter__ = AsyncMock(return_value=mock_session)
        inst.__aexit__ = AsyncMock(return_value=None)
        return inst

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        first, second = _make_context_client(), _make_context_client()
        first.schema = cached_schema
        second.schema = None
        mock_client_cls.side_effect = [first, second]

        base = HttpxGraphQLExecutor(url=GRAPHQL_URL, auth=_bearer(), cache_schema=True)
        assert await base.execute_query(query, variables) == {"one": 1}
        assert await base.execute_query(query, variables) == {"two": 2}

    assert mock_client_cls.call_count == 2
    assert (
        mock_client_cls.call_args_list[0].kwargs["fetch_schema_from_transport"] is True
    )
    assert mock_client_cls.call_args_list[1].kwargs["fetch_schema_from_transport"] is (
        False
    )
    assert mock_client_cls.call_args_list[1].kwargs["schema"] is cached_schema


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_bubbles_up_execute_errors_unchanged():
    """Test execute_query does not wrap exceptions raised by the GraphQL session."""
    query = _sample_query()
    variables = {"x": 1}
    expected_error = RuntimeError("boom")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=expected_error)

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        base = HttpxGraphQLExecutor(url=GRAPHQL_URL, auth=_bearer())

        with pytest.raises(RuntimeError) as exc:
            await base.execute_query(query, variables)

    assert exc.value is expected_error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_forwards_get_execution_result_false():
    """Default path asks gql for the data dict (raise-on-errors semantics)."""
    query = _sample_query()
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"ok": True})

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        base = HttpxGraphQLExecutor(url=GRAPHQL_URL, auth=_bearer())
        await base.execute_query(query, {})

    assert mock_session.execute.call_args.kwargs["get_execution_result"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_allow_partial_returns_execution_result_without_raising():
    """Partial path forwards get_execution_result=True and returns the result as-is.

    gql does not raise on GraphQL ``errors`` in this mode, so per-node failures
    arrive on ``result.errors`` next to the partial ``result.data``.
    """
    query = _sample_query()
    sentinel = ExecutionResult(
        data={"automations": {"edges": []}},
        errors=[GraphQLError("Permission denied", extensions={"code": "X"})],
    )
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=sentinel)

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        base = HttpxGraphQLExecutor(url=GRAPHQL_URL, auth=_bearer())
        result = await base.execute_query_allow_partial(query, {"x": 1})

    assert result is sentinel
    assert mock_session.execute.call_args.kwargs["get_execution_result"] is True


@pytest.mark.unit
def test_init_connects_to_given_url():
    """The executor connects to exactly the URL it is handed, no derivation."""
    url = "https://api.pipefy.com/graphql/interfaces"
    base = HttpxGraphQLExecutor(url=url, auth=_bearer())
    assert base._graphql_url == url


@pytest.mark.unit
def test_init_defaults_cache_schema_to_false():
    """Schema caching is off unless explicitly enabled."""
    base = HttpxGraphQLExecutor(url=GRAPHQL_URL, auth=_bearer())
    assert base._cache_schema is False


@pytest.mark.unit
def test_init_defaults_headers_to_none():
    """No telemetry headers unless the executor is handed them."""
    base = HttpxGraphQLExecutor(url=GRAPHQL_URL, auth=_bearer())
    assert base._headers is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_sends_telemetry_headers_on_the_request():
    """Headers handed to the executor ride the real outbound GraphQL request.

    Runs the real gql Client and httpx client, swapping only the network
    transport for an ``httpx.MockTransport`` that captures the sent headers; the
    telemetry headers must land and the bearer auth must still apply.
    """
    headers = telemetry_headers(surface="mcp", version=__version__)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"data": {"__typename": "Query"}})

    def transport_factory(**kwargs):
        kwargs.pop("verify", None)
        return HTTPXAsyncTransport(**kwargs, transport=httpx.MockTransport(handler))

    with patch(
        "pipefy_sdk.graphql_executor.HTTPXAsyncTransport", side_effect=transport_factory
    ):
        executor = HttpxGraphQLExecutor(
            url=GRAPHQL_URL, auth=_bearer(), headers=headers
        )
        await executor.execute_query(_sample_query(), {})

    sent = captured["headers"]
    assert sent["user-agent"] == f"pipefy-sdk/{__version__} (mcp)"
    assert sent["x-client-name"] == "mcp"
    assert sent["x-client-version"] == __version__
    assert sent["authorization"] == "Bearer test-token"
