"""Unit tests for the stateless iPaaS gateway (respx-mocked chain)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from pipefy_mcp.core.ipaas_gateway import IpaasGateway, IpaasGatewayError

IPAAS_URL = "https://ipaas.test"
REDIRECT_URI = "https://localhost/pipefy-mcp-callback"

TOOLS = [
    {
        "name": "ap_create_flow",
        "description": "Create a new flow\n\nLonger guidance here.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}},
    },
    {
        "name": "ap_list_flows",
        "description": "List flows in the current project",
        "inputSchema": {"type": "object"},
    },
]


@pytest.fixture
def gateway() -> IpaasGateway:
    return IpaasGateway(
        url=IPAAS_URL,
        oauth_client_id="client-id",
        oauth_client_secret="client-secret",
        oauth_redirect_uri=REDIRECT_URI,
    )


def _mock_happy_chain(respx_mock: respx.MockRouter, *, sse_tools_list: bool = False):
    """Wire every endpoint of the chain; return the /mcp route for inspection."""
    respx_mock.post(f"{IPAAS_URL}/api/v1/managed-authn/external-token").respond(
        200, json={"token": "session-token", "projectId": "proj-1"}
    )
    respx_mock.get(url__startswith=f"{IPAAS_URL}/authorize").respond(
        302,
        headers={"location": f"{IPAAS_URL}/mcp-authorize?authRequestId=auth-req-jwt"},
    )
    respx_mock.post(f"{IPAAS_URL}/api/v1/mcp-oauth/approve").respond(
        200, json={"redirectUrl": f"{REDIRECT_URI}?code=auth-code"}
    )
    respx_mock.post(f"{IPAAS_URL}/token").respond(
        200, json={"access_token": "access-token", "expires_in": 900}
    )

    tools_result = {"jsonrpc": "2.0", "id": 2, "result": {"tools": TOOLS}}

    def mcp_responder(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "initialize":
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}
            )
        if sse_tools_list:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=f"event: message\ndata: {json.dumps(tools_result)}\n\n",
            )
        return httpx.Response(200, json=tools_result)

    return respx_mock.post(f"{IPAAS_URL}/mcp").mock(side_effect=mcp_responder)


@pytest.mark.anyio
@respx.mock
async def test_list_tools_walks_the_full_chain(respx_mock, gateway):
    mcp_route = _mock_happy_chain(respx_mock)

    tools = await gateway.list_tools("embed-jwt")

    assert tools == TOOLS
    # The approve step authenticates with the exchanged session token and
    # targets the exchanged project.
    approve_request = respx_mock.routes[2].calls.last.request
    assert approve_request.headers["authorization"] == "Bearer session-token"
    assert json.loads(approve_request.content) == {
        "authRequestId": "auth-req-jwt",
        "projectId": "proj-1",
    }
    # The token exchange replays the PKCE verifier matching the challenge sent
    # to /authorize, plus the confidential client credentials.
    authorize_query = parse_qs(
        urlparse(str(respx_mock.routes[1].calls.last.request.url)).query
    )
    token_form = parse_qs(respx_mock.routes[3].calls.last.request.content.decode())
    assert token_form["client_id"] == ["client-id"]
    assert token_form["client_secret"] == ["client-secret"]
    assert token_form["redirect_uri"] == [REDIRECT_URI]
    assert authorize_query["code_challenge_method"] == ["S256"]
    assert token_form["code_verifier"][0]  # present and non-empty
    # The MCP endpoint sees initialize then tools/list with the access token.
    assert mcp_route.call_count == 2
    assert (
        mcp_route.calls.last.request.headers["authorization"] == "Bearer access-token"
    )


@pytest.mark.anyio
@respx.mock
async def test_public_client_omits_client_secret(respx_mock):
    """The default public PKCE client has no secret; the token form must not send one."""
    _mock_happy_chain(respx_mock)
    public_gateway = IpaasGateway(
        url=IPAAS_URL,
        oauth_client_id="public-client-id",
        oauth_redirect_uri=REDIRECT_URI,
    )

    tools = await public_gateway.list_tools("embed-jwt")

    assert tools == TOOLS
    token_form = parse_qs(respx_mock.routes[3].calls.last.request.content.decode())
    assert "client_secret" not in token_form
    assert token_form["client_id"] == ["public-client-id"]
    assert token_form["code_verifier"][0]


@pytest.mark.anyio
@respx.mock
async def test_list_tools_parses_sse_encoded_response(respx_mock, gateway):
    _mock_happy_chain(respx_mock, sse_tools_list=True)

    tools = await gateway.list_tools("embed-jwt")

    assert tools == TOOLS


@pytest.mark.anyio
@respx.mock
async def test_session_exchange_failure_names_the_step(respx_mock, gateway):
    respx_mock.post(f"{IPAAS_URL}/api/v1/managed-authn/external-token").respond(
        401, json={"error": "invalid token"}
    )

    with pytest.raises(IpaasGatewayError, match="session exchange.*401"):
        await gateway.list_tools("embed-jwt")


@pytest.mark.anyio
@respx.mock
async def test_unknown_oauth_client_is_reported_clearly(respx_mock, gateway):
    respx_mock.post(f"{IPAAS_URL}/api/v1/managed-authn/external-token").respond(
        200, json={"token": "session-token", "projectId": "proj-1"}
    )
    # An unknown client_id makes /authorize answer 400 instead of redirecting.
    respx_mock.get(url__startswith=f"{IPAAS_URL}/authorize").respond(
        400, json={"error": "invalid_client"}
    )

    with pytest.raises(IpaasGatewayError, match="authorization request.*400"):
        await gateway.list_tools("embed-jwt")


@pytest.mark.anyio
@respx.mock
async def test_redirect_without_auth_request_id_is_reported(respx_mock, gateway):
    respx_mock.post(f"{IPAAS_URL}/api/v1/managed-authn/external-token").respond(
        200, json={"token": "session-token", "projectId": "proj-1"}
    )
    respx_mock.get(url__startswith=f"{IPAAS_URL}/authorize").respond(
        302, headers={"location": f"{IPAAS_URL}/mcp-authorize"}
    )

    with pytest.raises(IpaasGatewayError, match="no authRequestId"):
        await gateway.list_tools("embed-jwt")


@pytest.mark.anyio
@respx.mock
async def test_jsonrpc_error_from_tools_list_raises(respx_mock, gateway):
    respx_mock.post(f"{IPAAS_URL}/api/v1/managed-authn/external-token").respond(
        200, json={"token": "session-token", "projectId": "proj-1"}
    )
    respx_mock.get(url__startswith=f"{IPAAS_URL}/authorize").respond(
        302,
        headers={"location": f"{IPAAS_URL}/mcp-authorize?authRequestId=auth-req-jwt"},
    )
    respx_mock.post(f"{IPAAS_URL}/api/v1/mcp-oauth/approve").respond(
        200, json={"redirectUrl": f"{REDIRECT_URI}?code=auth-code"}
    )
    respx_mock.post(f"{IPAAS_URL}/token").respond(
        200, json={"access_token": "access-token"}
    )
    respx_mock.post(f"{IPAAS_URL}/mcp").respond(
        200,
        json={"jsonrpc": "2.0", "id": 2, "error": {"code": -32603, "message": "boom"}},
    )

    with pytest.raises(IpaasGatewayError, match="tools/list returned an error"):
        await gateway.list_tools("embed-jwt")
