"""Unit tests for InternalApiClient and PipefySettings.internal_api_url.

Tests validate the internal API client behavior without real network calls.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from pipefy_mcp.services.pipefy.internal_api_client import InternalApiClient
from pipefy_mcp.settings import PipefySettings, Settings

DEFAULT_INTERNAL_API_URL = "https://app.pipefy.com/internal_api"


@pytest.mark.unit
def test_pipefy_settings_internal_api_url_default():
    """Test that PipefySettings.internal_api_url defaults to the expected URL."""
    settings = PipefySettings()
    assert settings.internal_api_url == DEFAULT_INTERNAL_API_URL


@pytest.mark.unit
def test_internal_api_url_overridden_via_env(monkeypatch):
    """Test that internal_api_url can be overridden via PIPEFY_INTERNAL_API_URL."""
    custom_url = "https://custom.pipefy.com/internal_api"
    monkeypatch.setenv("PIPEFY_INTERNAL_API_URL", custom_url)
    settings = Settings()
    assert settings.pipefy.internal_api_url == custom_url


OAUTH_TOKEN_URL = "https://auth.pipefy.com/oauth/token"


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_sends_post_with_correct_headers_and_body(respx_mock):
    """Test execute_query sends POST with Authorization, Content-Type, and JSON body."""
    query_string = "mutation { test }"
    variables = {"key": "value"}
    expected_json = {"data": {"automation": {"id": "123"}}}

    respx_mock.post(OAUTH_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "test-bearer-token",
                "token_type": "bearer",
                "expires_in": 3600,
            },
        )
    )
    route = respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=expected_json)
    )

    client = InternalApiClient(
        url=DEFAULT_INTERNAL_API_URL,
        oauth_url=OAUTH_TOKEN_URL,
        oauth_client="client_id",
        oauth_secret="client_secret",
    )
    result = await client.execute_query(query_string, variables)

    assert route.called
    request = route.calls.last.request
    assert request.content
    body = json.loads(request.content)
    assert body == {"query": query_string, "variables": variables}
    assert "authorization" in (h.lower() for h in request.headers.keys())
    assert "content-type" in (h.lower() for h in request.headers.keys())
    assert result == expected_json.get("data", expected_json)


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_returns_parsed_json_response(respx_mock):
    """Test execute_query returns the parsed JSON response from the API."""
    api_response = {"data": {"automation": {"id": "456"}}}
    respx_mock.post(OAUTH_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "tok", "token_type": "bearer", "expires_in": 3600},
        )
    )
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=api_response)
    )

    client = InternalApiClient(
        url=DEFAULT_INTERNAL_API_URL,
        oauth_url=OAUTH_TOKEN_URL,
        oauth_client="client_id",
        oauth_secret="client_secret",
    )
    result = await client.execute_query("query { x }", {})

    assert result == {"automation": {"id": "456"}}


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_raises_on_non_2xx_response(respx_mock):
    """Test execute_query raises when HTTP response is not 2xx."""
    respx_mock.post(OAUTH_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "tok", "token_type": "bearer", "expires_in": 3600},
        )
    )
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(500, json={"error": "Internal Server Error"})
    )

    client = InternalApiClient(
        url=DEFAULT_INTERNAL_API_URL,
        oauth_url=OAUTH_TOKEN_URL,
        oauth_client="client_id",
        oauth_secret="client_secret",
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.execute_query("query { x }", {})


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_raises_on_graphql_errors_in_body(respx_mock):
    """Test execute_query detects GraphQL errors (HTTP 200 but errors in JSON) and raises."""
    graphql_error_response = {"errors": [{"message": "Something went wrong"}]}
    respx_mock.post(OAUTH_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "tok", "token_type": "bearer", "expires_in": 3600},
        )
    )
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    client = InternalApiClient(
        url=DEFAULT_INTERNAL_API_URL,
        oauth_url=OAUTH_TOKEN_URL,
        oauth_client="client_id",
        oauth_secret="client_secret",
    )

    with pytest.raises(ValueError, match=r"^Something went wrong$"):
        await client.execute_query("query { x }", {})


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
    respx_mock.post(OAUTH_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "tok", "token_type": "bearer", "expires_in": 3600},
        )
    )
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    client = InternalApiClient(
        url=DEFAULT_INTERNAL_API_URL,
        oauth_url=OAUTH_TOKEN_URL,
        oauth_client="client_id",
        oauth_secret="client_secret",
    )

    with pytest.raises(
        ValueError,
        match=r"Permission Denied \[code=PERMISSION_DENIED\] \[correlation_id=abc-123\]",
    ):
        await client.execute_query("query { x }", {})


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
    respx_mock.post(OAUTH_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "tok", "token_type": "bearer", "expires_in": 3600},
        )
    )
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    client = InternalApiClient(
        url=DEFAULT_INTERNAL_API_URL,
        oauth_url=OAUTH_TOKEN_URL,
        oauth_client="client_id",
        oauth_secret="client_secret",
    )

    with pytest.raises(
        ValueError,
        match=r"^Error one; Error two \[code=BAD_INPUT\]$",
    ):
        await client.execute_query("query { x }", {})


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False, assert_all_called=False)
async def test_execute_query_error_without_message_uses_fallback(respx_mock):
    """GraphQL error dict without message uses 'Unknown error' as the base text."""
    graphql_error_response = {
        "errors": [{"extensions": {"code": "UNKNOWN"}}],
    }
    respx_mock.post(OAUTH_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "tok", "token_type": "bearer", "expires_in": 3600},
        )
    )
    respx_mock.post(DEFAULT_INTERNAL_API_URL).mock(
        return_value=httpx.Response(200, json=graphql_error_response)
    )

    client = InternalApiClient(
        url=DEFAULT_INTERNAL_API_URL,
        oauth_url=OAUTH_TOKEN_URL,
        oauth_client="client_id",
        oauth_secret="client_secret",
    )

    with pytest.raises(
        ValueError,
        match=r"^Unknown error \[code=UNKNOWN\]$",
    ):
        await client.execute_query("query { x }", {})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_query_raises_on_timeout():
    """Test execute_query raises appropriate error when HTTP request times out."""
    mock_client = MagicMock()
    mock_client.post = AsyncMock(
        side_effect=httpx.TimeoutException("Request timed out")
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "pipefy_mcp.services.pipefy.internal_api_client.httpx.AsyncClient",
        return_value=mock_client,
    ):
        client = InternalApiClient(
            url=DEFAULT_INTERNAL_API_URL,
            oauth_url=OAUTH_TOKEN_URL,
            oauth_client="client_id",
            oauth_secret="client_secret",
        )

        with pytest.raises(httpx.TimeoutException):
            await client.execute_query("query { x }", {})


@pytest.mark.unit
def test_internal_api_client_rejects_http_url():
    with pytest.raises(ValueError, match="HTTPS"):
        InternalApiClient(
            url="http://app.pipefy.com/internal_api",
            oauth_url="https://auth.pipefy.com/oauth/token",
            oauth_client="id",
            oauth_secret="secret",
        )


@pytest.mark.unit
def test_internal_api_client_rejects_http_oauth_url():
    with pytest.raises(ValueError, match="HTTPS"):
        InternalApiClient(
            url="https://app.pipefy.com/internal_api",
            oauth_url="http://auth.pipefy.com/oauth/token",
            oauth_client="id",
            oauth_secret="secret",
        )
