from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from gql import gql
from gql.graphql_request import GraphQLRequest
from gql.transport.exceptions import TransportQueryError
from gql.transport.httpx import HTTPXAsyncTransport
from pipefy_auth import StaticBearerAuth

from pipefy_sdk import __version__
from pipefy_sdk.graphql_executor import GraphQLEndpoint
from pipefy_sdk.telemetry import telemetry_headers

GRAPHQL_URL = "https://api.pipefy.com/graphql"


def _bearer() -> StaticBearerAuth:
    return StaticBearerAuth("test-token")


@contextmanager
def _patched_transport(handler):
    """Route the executor's gql transport through an ``httpx.MockTransport``.

    Runs the real gql Client and httpx stack, swapping only the network so the
    executor's actual raise-on-errors behavior is exercised, not a mock's.
    """

    def transport_factory(**kwargs):
        kwargs.pop("verify", None)
        return HTTPXAsyncTransport(**kwargs, transport=httpx.MockTransport(handler))

    with patch(
        "pipefy_sdk.graphql_executor.HTTPXAsyncTransport", side_effect=transport_factory
    ):
        yield


def _sample_query() -> GraphQLRequest:
    return gql("{ __typename }")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_builds_transport_with_tls_verification():
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

        endpoint = GraphQLEndpoint(url=GRAPHQL_URL)
        await endpoint.execute(query, variables, auth=_bearer())

    mock_transport_cls.assert_called_once()
    assert mock_transport_cls.call_args.kwargs["verify"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_binds_the_passed_auth_on_the_transport():
    """The endpoint applies the per-call ``auth``, not one captured at construction."""
    query = _sample_query()
    variables: dict = {}
    auth = _bearer()
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"ok": True})

    with (
        patch("pipefy_sdk.graphql_executor.HTTPXAsyncTransport") as mock_transport_cls,
        patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls,
    ):
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        endpoint = GraphQLEndpoint(url=GRAPHQL_URL)
        await endpoint.execute(query, variables, auth=auth)

    assert mock_transport_cls.call_args.kwargs["auth"] is auth


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_passes_variables_to_session():
    """Test execute creates a session and passes variable_values unchanged."""
    query = _sample_query()
    variables = {"a": 1, "nested": {"b": 2}}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"ok": True})

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        endpoint = GraphQLEndpoint(url=GRAPHQL_URL)
        result = await endpoint.execute(query, variables, auth=_bearer())

    mock_session.execute.assert_called_once()
    request = mock_session.execute.call_args[0][0]
    assert isinstance(request, GraphQLRequest)
    assert request.variable_values == variables
    assert result.data == {"ok": True}
    assert mock_client_cls.call_args.kwargs["fetch_schema_from_transport"] is False
    assert "schema" not in mock_client_cls.call_args.kwargs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_omits_variable_values_for_empty_dict():
    """Empty variables omits variable_values on the bound GraphQLRequest."""
    query = _sample_query()
    variables: dict = {}

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"ok": True})

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        endpoint = GraphQLEndpoint(url=GRAPHQL_URL)
        await endpoint.execute(query, variables, auth=_bearer())

    request = mock_session.execute.call_args[0][0]
    assert isinstance(request, GraphQLRequest)
    assert request.variable_values is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_reuse_fetches_once_then_passes_cached_schema():
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

        endpoint = GraphQLEndpoint(url=GRAPHQL_URL, cache_schema=True)
        first_result = await endpoint.execute(query, variables, auth=_bearer())
        second_result = await endpoint.execute(query, variables, auth=_bearer())
        assert first_result.data == {"one": 1}
        assert second_result.data == {"two": 2}

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
async def test_execute_bubbles_up_execute_errors_unchanged():
    """Test execute does not wrap exceptions raised by the GraphQL session."""
    query = _sample_query()
    variables = {"x": 1}
    expected_error = RuntimeError("boom")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=expected_error)

    with patch("pipefy_sdk.graphql_executor.Client") as mock_client_cls:
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        endpoint = GraphQLEndpoint(url=GRAPHQL_URL)

        with pytest.raises(RuntimeError) as exc:
            await endpoint.execute(query, variables, auth=_bearer())

    assert exc.value is expected_error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_returns_data_and_errors_together():
    """A response mixing data and per-node errors becomes a GraphQLResult."""
    partial_body = {
        "data": {"automations": {"edges": [{"node": {"id": "25"}}]}},
        "errors": [
            {
                "message": "Permission denied",
                "extensions": {"code": "PERMISSION_DENIED", "automation_id": "124"},
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=partial_body)

    with _patched_transport(handler):
        endpoint = GraphQLEndpoint(url=GRAPHQL_URL)
        result = await endpoint.execute(_sample_query(), {}, auth=_bearer())

    assert result.data == {"automations": {"edges": [{"node": {"id": "25"}}]}}
    assert result.errors[0]["extensions"]["automation_id"] == "124"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_success_carries_no_errors():
    """An error-free response yields a GraphQLResult with an empty error list."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"automations": {"edges": []}}})

    with _patched_transport(handler):
        endpoint = GraphQLEndpoint(url=GRAPHQL_URL)
        result = await endpoint.execute(_sample_query(), {}, auth=_bearer())

    assert result.data == {"automations": {"edges": []}}
    assert result.errors == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_null_data_yields_empty_result():
    """A fully null response yields empty data with errors kept; classifying it is the caller's job."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": None,
                "errors": [{"message": "Couldn't find Organization with 'id'=999"}],
            },
        )

    with _patched_transport(handler):
        endpoint = GraphQLEndpoint(url=GRAPHQL_URL)
        result = await endpoint.execute(_sample_query(), {}, auth=_bearer())

    assert result.data == {}
    assert result.errors[0]["message"] == "Couldn't find Organization with 'id'=999"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_returns_data_on_success():
    """The raise-on-error convenience unwraps a clean response to its ``data`` dict."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"__typename": "Query"}})

    with _patched_transport(handler):
        endpoint = GraphQLEndpoint(url=GRAPHQL_URL)
        result = await endpoint.execute_query(_sample_query(), {}, auth=_bearer())

    assert result == {"__typename": "Query"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_raises_transport_query_error_with_structured_errors():
    """Without an error formatter, ``execute_query`` raises a ``TransportQueryError``
    that still carries the structured ``errors`` list the tool layer reads."""
    error_body = {
        "data": {"automations": {"edges": [{"node": {"id": "25"}}]}},
        "errors": [
            {
                "message": "Permission denied",
                "extensions": {"code": "PERMISSION_DENIED", "automation_id": "124"},
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=error_body)

    with _patched_transport(handler):
        endpoint = GraphQLEndpoint(url=GRAPHQL_URL)
        with pytest.raises(TransportQueryError) as excinfo:
            await endpoint.execute_query(_sample_query(), {}, auth=_bearer())

    assert excinfo.value.errors[0]["message"] == "Permission denied"
    assert excinfo.value.errors[0]["extensions"]["code"] == "PERMISSION_DENIED"
    # The tool layer's correlation-id and part of its code extraction regex only
    # str(exc), so pin that the reconstructed message still carries the code.
    assert "PERMISSION_DENIED" in str(excinfo.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_applies_error_formatter_when_configured():
    """With an error formatter, ``execute_query`` raises the formatter's message as a ValueError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"errors": [{"message": "boom", "extensions": {"code": "X"}}]}
        )

    with _patched_transport(handler):
        endpoint = GraphQLEndpoint(
            url=GRAPHQL_URL,
            on_graphql_error=lambda errs: "; ".join(e["message"] for e in errs),
        )
        with pytest.raises(ValueError, match=r"^boom$"):
            await endpoint.execute_query(_sample_query(), {}, auth=_bearer())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_ignores_error_formatter_when_configured():
    """The primitive never applies ``on_graphql_error``; that policy is ``execute_query``'s.

    On a formatter-configured endpoint, ``execute`` still returns a ``GraphQLResult``
    carrying the raw errors rather than raising the formatter's ``ValueError``. This
    pins the one semantic that separates the primitive from the convenience layer.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"errors": [{"message": "boom", "extensions": {"code": "X"}}]}
        )

    with _patched_transport(handler):
        endpoint = GraphQLEndpoint(
            url=GRAPHQL_URL,
            on_graphql_error=lambda errs: "; ".join(e["message"] for e in errs),
        )
        result = await endpoint.execute(_sample_query(), {}, auth=_bearer())

    assert result.data == {}
    assert result.errors[0]["message"] == "boom"
    assert result.errors[0]["extensions"]["code"] == "X"


@pytest.mark.unit
def test_init_connects_to_given_url():
    """The endpoint connects to exactly the URL it is handed, no derivation."""
    url = "https://api.pipefy.com/graphql/interfaces"
    endpoint = GraphQLEndpoint(url=url)
    assert endpoint._graphql_url == url


@pytest.mark.unit
def test_init_defaults_cache_schema_to_false():
    """Schema caching is off unless explicitly enabled."""
    endpoint = GraphQLEndpoint(url=GRAPHQL_URL)
    assert endpoint._cache_schema is False


@pytest.mark.unit
def test_init_defaults_headers_to_none():
    """No telemetry headers unless the endpoint is handed them."""
    endpoint = GraphQLEndpoint(url=GRAPHQL_URL)
    assert endpoint._headers is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_sends_telemetry_headers_on_the_request():
    """Headers handed to the endpoint ride the real outbound GraphQL request.

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
        endpoint = GraphQLEndpoint(url=GRAPHQL_URL, headers=headers)
        await endpoint.execute(_sample_query(), {}, auth=_bearer())

    sent = captured["headers"]
    assert sent["user-agent"] == f"pipefy-sdk/{__version__} (mcp)"
    assert sent["x-client-name"] == "mcp"
    assert sent["x-client-version"] == __version__
    assert sent["authorization"] == "Bearer test-token"
