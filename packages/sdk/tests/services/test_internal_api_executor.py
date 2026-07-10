"""Unit tests for the Internal API executor and PipefySettings.internal_api_url.

The internal endpoint raises ``PipefyGraphQLError`` on GraphQL errors, carrying
the raw ``errors`` list; code and correlation_id come off each error's
``extensions`` rather than a formatted message string.
"""

import json

import httpx
import pytest
import respx
from gql import gql
from gql.transport.exceptions import TransportConnectionFailed, TransportServerError
from pipefy_auth import StaticBearerAuth

from pipefy_sdk.client import build_executors
from pipefy_sdk.graphql_executor import GraphQLExecutor, PipefyGraphQLError
from pipefy_sdk.settings import PipefySettings

DEFAULT_INTERNAL_API_URL = "https://app.pipefy.com/internal_api"


def _build_executor() -> GraphQLExecutor:
    return build_executors(
        PipefySettings(),
        StaticBearerAuth("test-bearer-token"),
    ).internal


@pytest.mark.unit
def test_pipefy_settings_internal_api_url_default():
    """Test that PipefySettings.internal_api_url defaults to the expected URL."""
    settings = PipefySettings()
    assert settings.internal_api_url == DEFAULT_INTERNAL_API_URL


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_sends_post_with_correct_headers_and_body(respx_mock):
    """Test execute_query sends POST with Authorization, Content-Type, and JSON body."""
    query = gql("mutation { test }")
    variables = {"key": "value"}
    expected_json = {"data": {"automation": {"id": "123"}}}

    route = respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=expected_json)
    )

    client = _build_executor()
    result = await client.execute_query(query, variables)

    assert route.called
    request = route.calls.last.request
    assert request.content
    body = json.loads(request.content)
    # gql serialises the parsed AST back to a string (plus may attach
    # ``operationName``); pin only the contract we care about.
    assert body["variables"] == variables
    assert "test" in body["query"]
    assert "authorization" in (h.lower() for h in request.headers.keys())
    assert "content-type" in (h.lower() for h in request.headers.keys())
    assert result == expected_json["data"]


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_returns_parsed_json_response(respx_mock):
    """Test execute_query returns the parsed JSON response from the API."""
    api_response = {"data": {"automation": {"id": "456"}}}
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=api_response)
    )

    result = await _build_executor().execute_query(gql("query { x }"), {})
    assert result == {"automation": {"id": "456"}}


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_raises_on_non_2xx_response(respx_mock):
    """Test execute_query raises when HTTP response is not 2xx."""
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(500, json={"error": "Internal Server Error"})
    )

    # gql's HTTPXAsyncTransport wraps ``httpx.HTTPStatusError`` as
    # ``TransportServerError`` — same path as the public-API client.
    with pytest.raises(TransportServerError):
        await _build_executor().execute_query(gql("query { x }"), {})


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_raises_on_graphql_errors_in_body(respx_mock):
    """Test execute_query detects GraphQL errors (HTTP 200 but errors in JSON) and raises."""
    graphql_error_response = {"errors": [{"message": "Something went wrong"}]}
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    with pytest.raises(PipefyGraphQLError, match=r"^Something went wrong$"):
        await _build_executor().execute_query(gql("query { x }"), {})


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_error_includes_extensions_code_and_correlation_id(
    respx_mock,
):
    """The raised error carries extensions code and correlation_id in its structured errors."""
    graphql_error_response = {
        "errors": [
            {
                "message": "Permission Denied",
                "extensions": {
                    "code": "PERMISSION_DENIED",
                    "correlation_id": "abc-123",
                },
            }
        ]
    }
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    with pytest.raises(PipefyGraphQLError) as excinfo:
        await _build_executor().execute_query(gql("query { x }"), {})

    extensions = excinfo.value.errors[0]["extensions"]
    assert extensions["code"] == "PERMISSION_DENIED"
    assert extensions["correlation_id"] == "abc-123"
    assert str(excinfo.value) == "Permission Denied"


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_error_includes_correlation_id_when_code_absent(
    respx_mock,
):
    """``correlation_id`` is carried in the structured errors even without ``extensions.code``."""
    graphql_error_response = {
        "errors": [
            {
                "message": "Rate limited",
                "extensions": {"correlation_id": "corr-only-99"},
            }
        ]
    }
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    with pytest.raises(PipefyGraphQLError) as excinfo:
        await _build_executor().execute_query(gql("query { x }"), {})

    extensions = excinfo.value.errors[0]["extensions"]
    assert "code" not in extensions
    assert extensions["correlation_id"] == "corr-only-99"
    assert str(excinfo.value) == "Rate limited"


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_error_concatenates_multiple_errors(respx_mock):
    """Multiple GraphQL error messages are joined with '; ' in the raised message."""
    graphql_error_response = {
        "errors": [
            {"message": "Error one"},
            {"message": "Error two", "extensions": {"code": "BAD_INPUT"}},
        ]
    }
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    with pytest.raises(PipefyGraphQLError) as excinfo:
        await _build_executor().execute_query(gql("query { x }"), {})

    assert str(excinfo.value) == "Error one; Error two"
    assert [e.get("message") for e in excinfo.value.errors] == [
        "Error one",
        "Error two",
    ]
    assert excinfo.value.errors[1]["extensions"]["code"] == "BAD_INPUT"


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_error_without_message_uses_fallback(respx_mock):
    """GraphQL error dict without message uses 'Unknown error' as the joined text."""
    graphql_error_response = {
        "errors": [{"extensions": {"code": "UNKNOWN"}}],
    }
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    with pytest.raises(PipefyGraphQLError) as excinfo:
        await _build_executor().execute_query(gql("query { x }"), {})

    assert str(excinfo.value) == "Unknown error"
    assert excinfo.value.errors[0]["extensions"]["code"] == "UNKNOWN"


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_raises_on_timeout(respx_mock):
    """Test execute_query raises appropriate error when HTTP request times out."""
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    with pytest.raises(TransportConnectionFailed, match="timed out"):
        await _build_executor().execute_query(gql("query { x }"), {})
