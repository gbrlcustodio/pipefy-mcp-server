from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from gql import gql
from gql.graphql_request import GraphQLRequest
from pipefy_auth import StaticBearerAuth

from pipefy_sdk.graphql_executor import HttpxGraphQLExecutor
from pipefy_sdk.settings import PipefySettings


@pytest.fixture
def valid_settings() -> PipefySettings:
    return PipefySettings(base_url="https://api.pipefy.com")


def _bearer() -> StaticBearerAuth:
    return StaticBearerAuth("test-token")


def _sample_query() -> GraphQLRequest:
    return gql("{ __typename }")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_builds_transport_with_tls_verification(valid_settings):
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

        base = HttpxGraphQLExecutor(settings=valid_settings, auth=_bearer())
        await base.execute_query(query, variables)

    mock_transport_cls.assert_called_once()
    assert mock_transport_cls.call_args.kwargs["verify"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_passes_variables_to_session(valid_settings):
    """Test execute_query creates a session and passes variable_values unchanged."""
    query = _sample_query()
    variables = {"a": 1, "nested": {"b": 2}}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"ok": True})

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        base = HttpxGraphQLExecutor(settings=valid_settings, auth=_bearer())
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
async def test_execute_query_omits_variable_values_for_empty_dict(valid_settings):
    """Empty variables omits variable_values on the bound GraphQLRequest."""
    query = _sample_query()
    variables: dict = {}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"ok": True})

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        base = HttpxGraphQLExecutor(settings=valid_settings, auth=_bearer())
        await base.execute_query(query, variables)

    request = mock_session.execute.call_args[0][0]
    assert isinstance(request, GraphQLRequest)
    assert request.variable_values is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_reuse_fetches_once_then_passes_cached_schema(
    valid_settings,
):
    """With gql_reuse_fetched_graphql_schema, first Client run introspects; next reuses schema."""
    settings = valid_settings.model_copy(
        update={"gql_reuse_fetched_graphql_schema": True}
    )
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

        base = HttpxGraphQLExecutor(settings=settings, auth=_bearer())
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
async def test_execute_query_bubbles_up_execute_errors_unchanged(valid_settings):
    """Test execute_query does not wrap exceptions raised by the GraphQL session."""
    query = _sample_query()
    variables = {"x": 1}
    expected_error = RuntimeError("boom")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=expected_error)

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        base = HttpxGraphQLExecutor(settings=valid_settings, auth=_bearer())

        with pytest.raises(RuntimeError) as exc:
            await base.execute_query(query, variables)

    assert exc.value is expected_error


@pytest.mark.unit
def test_init_accepts_url_override():
    """``url_override`` lets callers point an executor at a sibling endpoint."""
    settings = PipefySettings(base_url="https://api.pipefy.com")
    base = HttpxGraphQLExecutor(
        settings=settings,
        auth=_bearer(),
        url_override="https://api.pipefy.com/graphql/interfaces",
    )
    assert base._graphql_url == "https://api.pipefy.com/graphql/interfaces"


@pytest.mark.unit
def test_init_defaults_to_settings_graphql_url():
    """Without ``url_override`` the client uses ``settings.graphql_url``."""
    settings = PipefySettings(base_url="https://api.pipefy.com")
    base = HttpxGraphQLExecutor(settings=settings, auth=_bearer())
    assert base._graphql_url == "https://api.pipefy.com/graphql"
