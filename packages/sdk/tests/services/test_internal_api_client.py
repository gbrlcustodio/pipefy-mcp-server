"""Unit tests for InternalApiClient and PipefySettings.internal_api_url.

These tests intentionally assert the full GraphQL error text produced by
``InternalApiClient`` (including ``[code=...]`` / ``[correlation_id=...]``
suffixes).
"""

import json

import httpx
import pytest
import respx
from gql import gql
from gql.transport.exceptions import TransportConnectionFailed, TransportServerError
from pipefy_auth import StaticBearerAuth

from pipefy_sdk.services.internal_api_client import InternalApiClient
from pipefy_sdk.settings import PipefySettings

DEFAULT_INTERNAL_API_URL = "https://app.pipefy.com/internal_api"


def _build_client(
    url: str = DEFAULT_INTERNAL_API_URL,
    *,
    allow_insecure_urls: bool = False,
) -> InternalApiClient:
    return InternalApiClient(
        url=url,
        auth=StaticBearerAuth("test-bearer-token"),
        allow_insecure_urls=allow_insecure_urls,
    )


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

    client = _build_client()
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

    result = await _build_client().execute_query(gql("query { x }"), {})
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
        await _build_client().execute_query(gql("query { x }"), {})


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_raises_on_graphql_errors_in_body(respx_mock):
    """Test execute_query detects GraphQL errors (HTTP 200 but errors in JSON) and raises."""
    graphql_error_response = {"errors": [{"message": "Something went wrong"}]}
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    with pytest.raises(ValueError, match=r"^Something went wrong$"):
        await _build_client().execute_query(gql("query { x }"), {})


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_error_includes_extensions_code_and_correlation_id(
    respx_mock,
):
    """GraphQL error message includes extensions code and correlation_id when present."""
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

    with pytest.raises(
        ValueError,
        match=r"Permission Denied \[code=PERMISSION_DENIED\] \[correlation_id=abc-123\]",
    ):
        await _build_client().execute_query(gql("query { x }"), {})


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_error_includes_correlation_id_when_code_absent(
    respx_mock,
):
    """``correlation_id`` is appended even when ``extensions.code`` is missing."""
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

    with pytest.raises(
        ValueError,
        match=r"^Rate limited \[correlation_id=corr-only-99\]$",
    ):
        await _build_client().execute_query(gql("query { x }"), {})


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_error_concatenates_multiple_errors(respx_mock):
    """Multiple GraphQL errors are joined with '; ' in the raised ValueError message."""
    graphql_error_response = {
        "errors": [
            {"message": "Error one"},
            {"message": "Error two", "extensions": {"code": "BAD_INPUT"}},
        ]
    }
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    with pytest.raises(
        ValueError,
        match=r"^Error one; Error two \[code=BAD_INPUT\]$",
    ):
        await _build_client().execute_query(gql("query { x }"), {})


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_error_without_message_uses_fallback(respx_mock):
    """GraphQL error dict without message uses 'Unknown error' as the base text."""
    graphql_error_response = {
        "errors": [{"extensions": {"code": "UNKNOWN"}}],
    }
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    with pytest.raises(
        ValueError,
        match=r"^Unknown error \[code=UNKNOWN\]$",
    ):
        await _build_client().execute_query(gql("query { x }"), {})


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_raises_on_timeout(respx_mock):
    """Test execute_query raises appropriate error when HTTP request times out."""
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    with pytest.raises(TransportConnectionFailed, match="timed out"):
        await _build_client().execute_query(gql("query { x }"), {})


@pytest.mark.unit
def test_internal_api_client_rejects_http_url():
    with pytest.raises(ValueError, match="HTTPS"):
        _build_client(url="http://app.pipefy.com/internal_api")


@pytest.mark.unit
def test_internal_api_client_rejects_empty_hostname():
    with pytest.raises(ValueError, match="hostname"):
        _build_client(url="https://")


@pytest.mark.unit
def test_internal_api_client_rejects_localhost():
    with pytest.raises(ValueError, match="localhost"):
        _build_client(url="https://localhost/internal_api")


@pytest.mark.unit
def test_internal_api_client_rejects_private_literal_ip():
    with pytest.raises(ValueError, match="private|loopback|link-local"):
        _build_client(url="https://10.0.0.1/internal_api")


@pytest.mark.unit
def test_internal_api_client_allow_insecure_accepts_http():
    _build_client(url="http://127.0.0.1/internal_api", allow_insecure_urls=True)
