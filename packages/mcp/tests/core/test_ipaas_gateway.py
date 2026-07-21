"""Unit tests for the stateless iPaaS gateway (respx-mocked chain)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from pipefy_mcp.core.ipaas_gateway import (
    CALL_TIMEOUT_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    IpaasGateway,
    IpaasGatewayError,
)

IPAAS_URL = "https://ipaas.test"
REDIRECT_URI = "https://localhost/pipefy-mcp-callback"

TOOLS = [
    {
        "name": "demo_create_flow",
        "description": "Create a new flow\n\nLonger guidance here.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}},
    },
    {
        "name": "demo_list_flows",
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


def _mock_auth_chain(respx_mock: respx.MockRouter) -> None:
    """Wire every endpoint of the chain before /mcp (session + headless OAuth)."""
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


def _mock_happy_chain(
    respx_mock: respx.MockRouter,
    *,
    sse_tools_list: bool = False,
    rpc_result: dict | None = None,
):
    """Wire every endpoint of the chain; return the /mcp route for inspection.

    ``rpc_result`` is the JSON-RPC ``result`` the non-initialize MCP request
    answers with; it defaults to the ``tools/list`` catalog.
    """
    _mock_auth_chain(respx_mock)

    tools_result = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {"tools": TOOLS} if rpc_result is None else rpc_result,
    }

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
    _mock_auth_chain(respx_mock)
    respx_mock.post(f"{IPAAS_URL}/mcp").respond(
        200,
        json={"jsonrpc": "2.0", "id": 2, "error": {"code": -32603, "message": "boom"}},
    )

    with pytest.raises(IpaasGatewayError, match="tools/list returned an error"):
        await gateway.list_tools("embed-jwt")


CALL_RESULT = {
    "content": [{"type": "text", "text": "flow created: flow-1"}],
    "isError": False,
}


@pytest.mark.anyio
@respx.mock
async def test_call_tool_posts_tools_call_with_arguments(respx_mock, gateway):
    mcp_route = _mock_happy_chain(respx_mock, rpc_result=CALL_RESULT)

    result = await gateway.call_tool(
        "embed-jwt", "demo_create_flow", {"name": "My flow"}
    )

    assert result == CALL_RESULT
    body = json.loads(mcp_route.calls.last.request.content)
    assert body["method"] == "tools/call"
    assert body["params"] == {
        "name": "demo_create_flow",
        "arguments": {"name": "My flow"},
    }
    assert (
        mcp_route.calls.last.request.headers["authorization"] == "Bearer access-token"
    )


@pytest.mark.anyio
@respx.mock
async def test_call_tool_defaults_arguments_to_empty_object(respx_mock, gateway):
    mcp_route = _mock_happy_chain(respx_mock, rpc_result=CALL_RESULT)

    await gateway.call_tool("embed-jwt", "demo_list_flows")

    body = json.loads(mcp_route.calls.last.request.content)
    assert body["params"] == {"name": "demo_list_flows", "arguments": {}}


@pytest.mark.anyio
@respx.mock
async def test_call_tool_gives_only_the_invocation_hop_the_long_timeout(
    respx_mock, gateway
):
    """A called tool may run a real flow; the handshake hops keep 30s."""
    mcp_route = _mock_happy_chain(respx_mock, rpc_result=CALL_RESULT)

    await gateway.call_tool("embed-jwt", "demo_test_flow", {"flowId": "flow-1"})

    initialize, invocation = mcp_route.calls[-2].request, mcp_route.calls[-1].request
    assert initialize.extensions["timeout"]["read"] == REQUEST_TIMEOUT_SECONDS
    assert invocation.extensions["timeout"]["read"] == CALL_TIMEOUT_SECONDS


@pytest.mark.anyio
@respx.mock
async def test_call_tool_relays_host_error_results_without_raising(respx_mock, gateway):
    """A tool-level isError is data for the caller, not a chain failure."""
    error_result = {
        "content": [{"type": "text", "text": "flow not found"}],
        "isError": True,
    }
    _mock_happy_chain(respx_mock, rpc_result=error_result)

    result = await gateway.call_tool("embed-jwt", "demo_delete_flow", {"id": "nope"})

    assert result == error_result


@pytest.mark.anyio
@respx.mock
async def test_call_tool_parses_sse_encoded_response(respx_mock, gateway):
    _mock_happy_chain(respx_mock, sse_tools_list=True, rpc_result=CALL_RESULT)

    result = await gateway.call_tool("embed-jwt", "demo_create_flow", {"name": "x"})

    assert result == CALL_RESULT


@pytest.mark.anyio
@respx.mock
async def test_jsonrpc_error_from_tools_call_names_the_method(respx_mock, gateway):
    _mock_auth_chain(respx_mock)
    respx_mock.post(f"{IPAAS_URL}/mcp").respond(
        200,
        json={"jsonrpc": "2.0", "id": 2, "error": {"code": -32602, "message": "boom"}},
    )

    with pytest.raises(IpaasGatewayError, match="tools/call returned an error"):
        await gateway.call_tool("embed-jwt", "demo_create_flow", {})


@pytest.mark.anyio
@respx.mock
async def test_call_tool_timeout_names_the_method_and_points_at_runs(
    respx_mock, gateway
):
    """A timeout on the invocation hop must not surface as a bare httpx error."""
    _mock_auth_chain(respx_mock)

    def responder(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})
        raise httpx.ReadTimeout("read timed out")

    respx_mock.post(f"{IPAAS_URL}/mcp").mock(side_effect=responder)

    with pytest.raises(
        IpaasGatewayError, match="tools/call timed out after 120s.*run-listing"
    ):
        await gateway.call_tool("embed-jwt", "demo_test_flow", {"flowId": "flow-1"})


@pytest.mark.anyio
@respx.mock
async def test_handshake_timeout_reports_retry_safe(respx_mock, gateway):
    """An initialize timeout means nothing ran — not a long-running tool."""
    _mock_auth_chain(respx_mock)

    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out")

    respx_mock.post(f"{IPAAS_URL}/mcp").mock(side_effect=responder)

    with pytest.raises(IpaasGatewayError, match="handshake timed out.*safe to retry"):
        await gateway.call_tool("embed-jwt", "demo_test_flow", {"flowId": "flow-1"})


@pytest.mark.anyio
@respx.mock
async def test_response_without_result_names_the_method(respx_mock, gateway):
    _mock_auth_chain(respx_mock)
    respx_mock.post(f"{IPAAS_URL}/mcp").respond(200, json={"jsonrpc": "2.0", "id": 2})

    with pytest.raises(IpaasGatewayError, match="tools/call.*no result"):
        await gateway.call_tool("embed-jwt", "demo_list_flows")


PIECE_NAME = "@example/piece-demo"


def _mock_session_only(respx_mock: respx.MockRouter) -> None:
    """Connection endpoints authenticate with the session alone (no OAuth)."""
    respx_mock.post(f"{IPAAS_URL}/api/v1/managed-authn/external-token").respond(
        200, json={"token": "session-token", "projectId": "proj-1"}
    )


@pytest.mark.anyio
@respx.mock
async def test_connection_auth_url_builds_url_and_completion_bundle(
    respx_mock, gateway
):
    _mock_session_only(respx_mock)
    respx_mock.get(f"{IPAAS_URL}/api/v1/pieces/{PIECE_NAME}").respond(
        200, json={"auth": {"type": "OAUTH2", "scope": ["chat:write", "read"]}}
    )
    respx_mock.get(f"{IPAAS_URL}/api/v1/oauth-apps").respond(
        200,
        json={"data": [{"pieceName": PIECE_NAME, "clientId": "deployment-client"}]},
    )
    auth_url_route = respx_mock.post(
        f"{IPAAS_URL}/api/v1/app-connections/oauth2/authorization-url"
    ).respond(
        200,
        json={
            "authorizationUrl": "https://third-party.test/consent?x=1",
            "codeVerifier": "the-verifier",
        },
    )

    result = await gateway.connection_auth_url("embed-jwt", PIECE_NAME)

    assert result["authorization_url"] == "https://third-party.test/consent?x=1"
    assert result["completion"] == {
        "type": "PLATFORM_OAUTH2",
        "client_id": "deployment-client",
        "redirect_url": f"{IPAAS_URL}/redirect",
        "scope": "chat:write read",
        "code_verifier": "the-verifier",
    }
    request = auth_url_route.calls.last.request
    assert request.headers["authorization"] == "Bearer session-token"
    assert json.loads(request.content) == {
        "pieceName": PIECE_NAME,
        "clientId": "deployment-client",
        "redirectUrl": f"{IPAAS_URL}/redirect",
    }


@pytest.mark.anyio
@respx.mock
async def test_connection_auth_url_joins_string_scope_verbatim(respx_mock, gateway):
    """A piece publishing its scope as one string must not be split per char."""
    _mock_session_only(respx_mock)
    respx_mock.get(f"{IPAAS_URL}/api/v1/pieces/{PIECE_NAME}").respond(
        200, json={"auth": {"type": "OAUTH2", "scope": "chat:write read"}}
    )
    respx_mock.get(f"{IPAAS_URL}/api/v1/oauth-apps").respond(
        200, json={"data": [{"pieceName": PIECE_NAME, "clientId": "c"}]}
    )
    respx_mock.post(
        f"{IPAAS_URL}/api/v1/app-connections/oauth2/authorization-url"
    ).respond(200, json={"authorizationUrl": "https://third-party.test/consent"})

    result = await gateway.connection_auth_url("embed-jwt", PIECE_NAME)

    assert result["completion"]["scope"] == "chat:write read"


@pytest.mark.anyio
@respx.mock
async def test_oauth_client_lookup_follows_pagination(respx_mock, gateway):
    _mock_session_only(respx_mock)
    respx_mock.get(f"{IPAAS_URL}/api/v1/pieces/{PIECE_NAME}").respond(
        200, json={"auth": {"type": "OAUTH2", "scope": []}}
    )
    apps_route = respx_mock.get(f"{IPAAS_URL}/api/v1/oauth-apps").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "data": [{"pieceName": "@example/piece-other", "clientId": "x"}],
                    "next": "cursor-2",
                },
            ),
            httpx.Response(
                200,
                json={"data": [{"pieceName": PIECE_NAME, "clientId": "page2-client"}]},
            ),
        ]
    )
    respx_mock.post(
        f"{IPAAS_URL}/api/v1/app-connections/oauth2/authorization-url"
    ).respond(200, json={"authorizationUrl": "https://third-party.test/consent"})

    result = await gateway.connection_auth_url("embed-jwt", PIECE_NAME)

    assert result["completion"]["client_id"] == "page2-client"
    assert apps_route.call_count == 2
    assert "cursor=cursor-2" in str(apps_route.calls.last.request.url)


@pytest.mark.anyio
@respx.mock
async def test_connection_auth_url_rejects_non_oauth_pieces(respx_mock, gateway):
    _mock_session_only(respx_mock)
    respx_mock.get(f"{IPAAS_URL}/api/v1/pieces/{PIECE_NAME}").respond(
        200, json={"auth": {"type": "SECRET_TEXT"}}
    )

    with pytest.raises(IpaasGatewayError, match="does not use an OAuth connection"):
        await gateway.connection_auth_url("embed-jwt", PIECE_NAME)


@pytest.mark.anyio
@respx.mock
async def test_connection_auth_url_reports_missing_deployment_client(
    respx_mock, gateway
):
    _mock_session_only(respx_mock)
    respx_mock.get(f"{IPAAS_URL}/api/v1/pieces/{PIECE_NAME}").respond(
        200, json={"auth": {"type": "OAUTH2", "scope": []}}
    )
    respx_mock.get(f"{IPAAS_URL}/api/v1/oauth-apps").respond(200, json={"data": []})

    with pytest.raises(IpaasGatewayError, match="No OAuth client is configured"):
        await gateway.connection_auth_url("embed-jwt", PIECE_NAME)


@pytest.mark.anyio
@respx.mock
async def test_upsert_connection_posts_body_with_session_and_project(
    respx_mock, gateway
):
    _mock_session_only(respx_mock)
    upsert_route = respx_mock.post(f"{IPAAS_URL}/api/v1/app-connections").respond(
        201,
        json={
            "id": "conn-1",
            "externalId": "mcp-abc",
            "displayName": "Demo",
            "pieceName": PIECE_NAME,
            "status": "ACTIVE",
            "type": "SECRET_TEXT",
        },
    )

    connection = await gateway.upsert_connection(
        "embed-jwt",
        piece_name=PIECE_NAME,
        connection_type="SECRET_TEXT",
        value={"secret_text": "shh"},
        external_id="mcp-abc",
        display_name="Demo",
    )

    assert connection["id"] == "conn-1"
    request = upsert_route.calls.last.request
    assert request.headers["authorization"] == "Bearer session-token"
    assert json.loads(request.content) == {
        "externalId": "mcp-abc",
        "displayName": "Demo",
        "pieceName": PIECE_NAME,
        "projectId": "proj-1",
        "type": "SECRET_TEXT",
        "value": {"secret_text": "shh", "type": "SECRET_TEXT"},
    }


@pytest.mark.anyio
@respx.mock
async def test_upsert_connection_failure_names_the_step(respx_mock, gateway):
    _mock_session_only(respx_mock)
    respx_mock.post(f"{IPAAS_URL}/api/v1/app-connections").respond(
        400, json={"code": "INVALID_APP_CONNECTION", "params": {}}
    )

    with pytest.raises(IpaasGatewayError, match="connection upsert.*400"):
        await gateway.upsert_connection(
            "embed-jwt",
            piece_name=PIECE_NAME,
            connection_type="SECRET_TEXT",
            value={"secret_text": "bad"},
            external_id="mcp-abc",
            display_name="Demo",
        )


@pytest.mark.anyio
@respx.mock
async def test_sse_notification_frames_before_the_response_are_skipped(
    respx_mock, gateway
):
    """The response frame is selected by shape, not assumed to arrive first."""
    _mock_auth_chain(respx_mock)
    notification = {"jsonrpc": "2.0", "method": "notifications/message", "params": {}}
    response = {"jsonrpc": "2.0", "id": 2, "result": CALL_RESULT}
    sse_body = (
        f"event: message\ndata: {json.dumps(notification)}\n\n"
        f"event: message\ndata: {json.dumps(response)}\n\n"
    )

    def responder(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, text=sse_body
        )

    respx_mock.post(f"{IPAAS_URL}/mcp").mock(side_effect=responder)

    result = await gateway.call_tool("embed-jwt", "demo_create_flow", {"name": "x"})

    assert result == CALL_RESULT


@pytest.mark.anyio
@respx.mock
async def test_null_result_is_a_protocol_error(respx_mock, gateway):
    """A JSON-RPC success with an explicit null result is a gateway error, not None."""
    _mock_auth_chain(respx_mock)
    respx_mock.post(f"{IPAAS_URL}/mcp").respond(
        200, json={"jsonrpc": "2.0", "id": 2, "result": None}
    )

    with pytest.raises(IpaasGatewayError, match="tools/call.*non-object result"):
        await gateway.call_tool("embed-jwt", "demo_list_flows")


@pytest.mark.anyio
@respx.mock
async def test_session_exchange_missing_key_names_the_step(respx_mock, gateway):
    """A 200 with a body missing an expected key is a step error, not a raw KeyError."""
    respx_mock.post(f"{IPAAS_URL}/api/v1/managed-authn/external-token").respond(
        200, json={}
    )

    with pytest.raises(IpaasGatewayError, match="session exchange.*without 'token'"):
        await gateway.list_tools("embed-jwt")


@pytest.mark.anyio
@respx.mock
async def test_non_json_body_names_the_step(respx_mock, gateway):
    """A 200 whose body is not JSON is a step error, not a raw ValueError."""
    respx_mock.post(f"{IPAAS_URL}/api/v1/managed-authn/external-token").respond(
        200, text="<html>not json</html>", headers={"content-type": "text/html"}
    )

    with pytest.raises(IpaasGatewayError, match="session exchange.*not valid JSON"):
        await gateway.list_tools("embed-jwt")
