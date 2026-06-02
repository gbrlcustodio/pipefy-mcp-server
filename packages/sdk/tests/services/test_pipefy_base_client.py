from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pipefy_auth import StaticBearerAuth

from pipefy_sdk.base_client import BasePipefyClient
from pipefy_sdk.settings import PipefySettings


@pytest.fixture
def valid_settings() -> PipefySettings:
    return PipefySettings(base_url="https://api.pipefy.com")


def _bearer() -> StaticBearerAuth:
    return StaticBearerAuth("test-token")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_passes_variables_to_session(valid_settings):
    """Test execute_query creates a session and passes variable_values unchanged."""
    query = object()
    variables = {"a": 1, "nested": {"b": 2}}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"ok": True})

    with patch("pipefy_sdk.base_client.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        base = BasePipefyClient(settings=valid_settings, auth=_bearer())
        result = await base.execute_query(query, variables)

    mock_session.execute.assert_called_once_with(query, variable_values=variables)
    assert result == {"ok": True}
    assert mock_client_cls.call_args.kwargs["fetch_schema_from_transport"] is False
    assert "schema" not in mock_client_cls.call_args.kwargs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_reuse_fetches_once_then_passes_cached_schema(
    valid_settings,
):
    """With gql_reuse_fetched_graphql_schema, first Client run introspects; next reuses schema."""
    settings = valid_settings.model_copy(
        update={"gql_reuse_fetched_graphql_schema": True}
    )
    query = object()
    variables: dict = {}
    cached_schema = object()
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[{"one": 1}, {"two": 2}])

    def _make_context_client():
        inst = MagicMock()
        inst.__aenter__ = AsyncMock(return_value=mock_session)
        inst.__aexit__ = AsyncMock(return_value=None)
        return inst

    with patch("pipefy_sdk.base_client.Client") as mock_client_cls:
        first, second = _make_context_client(), _make_context_client()
        first.schema = cached_schema
        second.schema = None
        mock_client_cls.side_effect = [first, second]

        base = BasePipefyClient(settings=settings, auth=_bearer())
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
    query = object()
    variables = {"x": 1}
    expected_error = RuntimeError("boom")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=expected_error)

    with patch("pipefy_sdk.base_client.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        base = BasePipefyClient(settings=valid_settings, auth=_bearer())

        with pytest.raises(RuntimeError) as exc:
            await base.execute_query(query, variables)

    assert exc.value is expected_error


@pytest.mark.unit
def test_init_accepts_url_override():
    """``url_override`` lets callers point a BasePipefyClient at a sibling endpoint."""
    settings = PipefySettings(base_url="https://api.pipefy.com")
    base = BasePipefyClient(
        settings=settings,
        auth=_bearer(),
        url_override="https://api.pipefy.com/graphql/interfaces",
    )
    assert base._graphql_url == "https://api.pipefy.com/graphql/interfaces"


@pytest.mark.unit
def test_init_defaults_to_settings_graphql_url():
    """Without ``url_override`` the client uses ``settings.graphql_url``."""
    settings = PipefySettings(base_url="https://api.pipefy.com")
    base = BasePipefyClient(settings=settings, auth=_bearer())
    assert base._graphql_url == "https://api.pipefy.com/graphql"
