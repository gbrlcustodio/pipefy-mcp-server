"""Stateless gateway to a pipe's iPaaS (Advanced Automations) tool surface.

The gateway turns a pipe-scoped advanced-automations token (minted by the
Pipefy API, see ``PipefyClient.get_advanced_automations_token``) into an
authenticated ``tools/list`` against the pipe's iPaaS workspace:

1. Exchange the advanced-automations token for an iPaaS user session.
2. Run a headless OAuth authorization-code + PKCE flow with the deployment's
   pre-registered client — the authorize redirect is parsed, never followed,
   and the approve step is a plain authenticated POST — yielding a short-lived
   access token.
3. Call the iPaaS MCP endpoint (JSON-RPC ``initialize`` + ``tools/list``).

Every call is self-contained: no token, session, or client state is retained,
so any server replica can serve any call. The construction values come from
:class:`pipefy_mcp.settings.IpaasSettings` via the composition root; the
gateway itself reads no settings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from pipefy_auth.pkce import challenge_from_verifier, generate_verifier

REQUEST_TIMEOUT_SECONDS = 30
_MCP_PROTOCOL_VERSION = "2025-03-26"
_ERROR_BODY_PREVIEW_CHARS = 300


class IpaasGatewayError(RuntimeError):
    """A step of the iPaaS chain failed; the message is agent-facing."""


def _step_error(step: str, response: httpx.Response) -> IpaasGatewayError:
    preview = response.text[:_ERROR_BODY_PREVIEW_CHARS]
    return IpaasGatewayError(f"{step} failed (HTTP {response.status_code}): {preview}")


def _step_json(step: str, response: httpx.Response) -> dict[str, Any]:
    """Decode a JSON object body, mapping a non-JSON/non-object body to a step error.

    A 2xx status is not proof the body has the expected shape; without this a
    malformed body would surface to the agent as a bare ``ValueError`` rather
    than a message naming the step that misbehaved.
    """
    try:
        body = response.json()
    except ValueError as exc:
        raise IpaasGatewayError(
            f"{step} returned a body that is not valid JSON."
        ) from exc
    if not isinstance(body, dict):
        raise IpaasGatewayError(f"{step} returned a JSON body that is not an object.")
    return body


def _step_field(step: str, body: dict[str, Any], key: str) -> Any:
    """Read a required key, mapping its absence to a step-named error."""
    try:
        return body[key]
    except KeyError as exc:
        raise IpaasGatewayError(f"{step} returned a body without '{key}'.") from exc


@dataclass(frozen=True)
class IpaasGateway:
    """Stateless client for one iPaaS deployment (see module docstring)."""

    url: str
    oauth_client_id: str
    oauth_redirect_uri: str
    # Only for confidential (client_secret_post) registrations; the default
    # public PKCE client has no secret.
    oauth_client_secret: str | None = None

    async def list_tools(self, advanced_automations_token: str) -> list[dict[str, Any]]:
        """Return the MCP tool catalog of the pipe the token was minted for.

        Each entry is the wire-format tool object (``name``, ``description``,
        ``inputSchema``); filtering or trimming is the caller's concern.

        Args:
            advanced_automations_token: Pipe-scoped token from
                ``PipefyClient.get_advanced_automations_token``.

        Raises:
            IpaasGatewayError: When any step of the chain is refused by the
                iPaaS host; the message names the step.
        """
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
        ) as http:
            session_token, project_id = await self._exchange_session(
                http, advanced_automations_token
            )
            access_token = await self._oauth_access_token(
                http, session_token, project_id
            )
            return await self._tools_list(http, access_token)

    async def _exchange_session(
        self, http: httpx.AsyncClient, advanced_automations_token: str
    ) -> tuple[str, str]:
        """Exchange the pipe token for an iPaaS user session (token, project id)."""
        response = await http.post(
            f"{self.url}/api/v1/managed-authn/external-token",
            json={"externalAccessToken": advanced_automations_token},
        )
        if response.status_code not in (200, 201):
            raise _step_error("iPaaS session exchange", response)
        payload = _step_json("iPaaS session exchange", response)
        return (
            _step_field("iPaaS session exchange", payload, "token"),
            _step_field("iPaaS session exchange", payload, "projectId"),
        )

    async def _oauth_access_token(
        self, http: httpx.AsyncClient, session_token: str, project_id: str
    ) -> str:
        """Run the headless code + PKCE flow and return an access token."""
        verifier = generate_verifier()
        authorize_url = f"{self.url}/authorize?" + urlencode(
            {
                "client_id": self.oauth_client_id,
                "redirect_uri": self.oauth_redirect_uri,
                "response_type": "code",
                "code_challenge": challenge_from_verifier(verifier),
                "code_challenge_method": "S256",
            }
        )
        response = await http.get(authorize_url, follow_redirects=False)
        if response.status_code not in (301, 302, 303, 307):
            raise _step_error("iPaaS authorization request", response)
        auth_request_id = _query_param(
            response.headers.get("location", ""), "authRequestId"
        )
        if auth_request_id is None:
            raise IpaasGatewayError(
                "iPaaS authorization request returned no authRequestId; the "
                "configured OAuth client may be unknown to the iPaaS host or its "
                "redirect URI may not match the registration."
            )

        response = await http.post(
            f"{self.url}/api/v1/mcp-oauth/approve",
            json={"authRequestId": auth_request_id, "projectId": project_id},
            headers={"Authorization": f"Bearer {session_token}"},
        )
        if response.status_code != 200:
            raise _step_error("iPaaS authorization approval", response)
        approval = _step_json("iPaaS authorization approval", response)
        code = _query_param(approval.get("redirectUrl", ""), "code")
        if code is None:
            raise IpaasGatewayError(
                "iPaaS authorization approval returned no authorization code."
            )

        token_form = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": self.oauth_client_id,
            "redirect_uri": self.oauth_redirect_uri,
        }
        if self.oauth_client_secret:
            token_form["client_secret"] = self.oauth_client_secret
        response = await http.post(f"{self.url}/token", data=token_form)
        if response.status_code != 200:
            raise _step_error("iPaaS token exchange", response)
        return _step_field(
            "iPaaS token exchange",
            _step_json("iPaaS token exchange", response),
            "access_token",
        )

    async def _tools_list(
        self, http: httpx.AsyncClient, access_token: str
    ) -> list[dict[str, Any]]:
        """MCP handshake against the iPaaS endpoint; return the raw tool list."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            # The endpoint may answer plain JSON or a single SSE event.
            "Accept": "application/json, text/event-stream",
        }
        mcp_url = f"{self.url}/mcp"
        # The endpoint is stateless (no session id); initialize is informational
        # but keeps us honest with clients that enforce the MCP lifecycle.
        await http.post(
            mcp_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "pipefy-mcp-server", "version": "0"},
                },
            },
            headers=headers,
        )
        response = await http.post(
            mcp_url,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers=headers,
        )
        if response.status_code != 200:
            raise _step_error("iPaaS tools/list", response)
        payload = _parse_mcp_response(response)
        if "error" in payload:
            raise IpaasGatewayError(
                f"iPaaS tools/list returned an error: {payload['error']}"
            )
        result = _step_field("iPaaS tools/list", payload, "result")
        if not isinstance(result, dict):
            raise IpaasGatewayError("iPaaS tools/list returned a non-object result.")
        return _step_field("iPaaS tools/list", result, "tools")


def _query_param(url: str, name: str) -> str | None:
    values = parse_qs(urlparse(url).query).get(name)
    return values[0] if values else None


def _parse_mcp_response(response: httpx.Response) -> dict[str, Any]:
    """Decode a JSON-RPC response that may arrive as JSON or one SSE event."""
    if "text/event-stream" in response.headers.get("content-type", ""):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[len("data:") :].strip())
                except ValueError as exc:
                    raise IpaasGatewayError(
                        "iPaaS tools/list returned an event with a non-JSON data payload."
                    ) from exc
        raise IpaasGatewayError(
            "iPaaS MCP endpoint returned an event stream with no data event."
        )
    return _step_json("iPaaS tools/list", response)


__all__ = ["IpaasGateway", "IpaasGatewayError"]
