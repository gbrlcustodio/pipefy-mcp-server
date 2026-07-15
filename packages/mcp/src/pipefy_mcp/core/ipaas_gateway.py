"""Stateless gateway to a pipe's iPaaS (Advanced Automations) tool surface.

The gateway turns a pipe-scoped advanced-automations token (minted by the
Pipefy API, see ``PipefyClient.get_advanced_automations_token``) into an
authenticated ``tools/list`` against the pipe's iPaaS workspace:

1. Exchange the advanced-automations token for an iPaaS user session.
2. Run a headless OAuth authorization-code + PKCE flow with the deployment's
   pre-registered client — the authorize redirect is parsed, never followed,
   and the approve step is a plain authenticated POST — yielding a short-lived
   access token.
3. Call the iPaaS MCP endpoint (JSON-RPC ``initialize`` + ``tools/list`` or
   ``tools/call``).

Connection management (:meth:`IpaasGateway.connection_auth_url`,
:meth:`IpaasGateway.upsert_connection`) stops after step 1: those REST
endpoints authenticate with the exchanged user session itself, so the OAuth
steps do not apply to them.

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
# The invocation hop only: a called tool may execute a real flow (test runs,
# retries), which can legitimately outlast the 30s handshake budget.
CALL_TIMEOUT_SECONDS = 120
_MCP_PROTOCOL_VERSION = "2025-03-26"
_ERROR_BODY_PREVIEW_CHARS = 300


class IpaasGatewayError(RuntimeError):
    """A step of the iPaaS chain failed; the message is agent-facing."""


def _step_error(step: str, response: httpx.Response) -> IpaasGatewayError:
    preview = response.text[:_ERROR_BODY_PREVIEW_CHARS]
    return IpaasGatewayError(f"{step} failed (HTTP {response.status_code}): {preview}")


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
        result = await self._authed_mcp_request(
            advanced_automations_token, "tools/list", params={}
        )
        return result["tools"]

    async def call_tool(
        self,
        advanced_automations_token: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke one tool in the pipe's iPaaS workspace and return its raw result.

        The return value is the wire-format ``tools/call`` result
        (``content`` list plus ``isError``); interpreting or reshaping it is
        the caller's concern. Like :meth:`list_tools`, each call runs the full
        stateless auth chain; only the invocation hop itself gets the longer
        :data:`CALL_TIMEOUT_SECONDS` budget, since a called tool may execute a
        real flow.

        Args:
            advanced_automations_token: Pipe-scoped token from
                ``PipefyClient.get_advanced_automations_token``.
            tool_name: Exact catalog name (see :meth:`list_tools`).
            arguments: Tool arguments, forwarded verbatim; the iPaaS host
                validates them against its own input schema.

        Raises:
            IpaasGatewayError: When any step of the chain is refused by the
                iPaaS host; the message names the step.
        """
        return await self._authed_mcp_request(
            advanced_automations_token,
            "tools/call",
            params={"name": tool_name, "arguments": arguments or {}},
            timeout_seconds=CALL_TIMEOUT_SECONDS,
        )

    async def connection_auth_url(
        self, advanced_automations_token: str, piece_name: str
    ) -> dict[str, Any]:
        """Build the third-party consent URL for an OAuth piece.

        Connection endpoints authenticate with the exchanged user session
        directly — the MCP OAuth dance is not part of this chain. The return
        value pairs the URL the user must open with a ``completion`` bundle
        (client id, redirect URL, scope, PKCE verifier) that
        :meth:`upsert_connection`'s caller passes back verbatim, so the
        two-step flow needs no server-side state.

        Raises:
            IpaasGatewayError: When the piece does not use OAuth, no OAuth
                client is configured for it on the iPaaS host, or a step is
                refused; the message names the step.
        """
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
        ) as http:
            session_token, _ = await self._exchange_session(
                http, advanced_automations_token
            )
            headers = {"Authorization": f"Bearer {session_token}"}
            auth = await self._piece_oauth_metadata(http, headers, piece_name)
            client_id = await self._deployment_oauth_client_id(
                http, headers, piece_name
            )
            redirect_url = f"{self.url}/redirect"
            response = await http.post(
                f"{self.url}/api/v1/app-connections/oauth2/authorization-url",
                json={
                    "pieceName": piece_name,
                    "clientId": client_id,
                    "redirectUrl": redirect_url,
                },
                headers=headers,
            )
            if response.status_code != 200:
                raise _step_error("iPaaS authorization URL", response)
            payload = response.json()
        scope = auth.get("scope") or []
        completion = {
            "type": "PLATFORM_OAUTH2",
            "client_id": client_id,
            "redirect_url": redirect_url,
            "scope": " ".join(scope) if isinstance(scope, list) else str(scope),
        }
        if payload.get("codeVerifier"):
            completion["code_verifier"] = payload["codeVerifier"]
        return {
            "authorization_url": payload["authorizationUrl"],
            "completion": completion,
        }

    async def upsert_connection(
        self,
        advanced_automations_token: str,
        *,
        piece_name: str,
        connection_type: str,
        value: dict[str, Any],
        external_id: str,
        display_name: str,
    ) -> dict[str, Any]:
        """Create (or, on an existing ``external_id``, replace) a connection.

        Returns the created connection's wire object. The caller must not
        relay it wholesale: pick the non-sensitive fields, since the create
        response is not guaranteed to be credential-free.

        Raises:
            IpaasGatewayError: When the iPaaS host refuses a step (including
                credential validation failures); the message names the step.
        """
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
        ) as http:
            session_token, project_id = await self._exchange_session(
                http, advanced_automations_token
            )
            response = await http.post(
                f"{self.url}/api/v1/app-connections",
                json={
                    "externalId": external_id,
                    "displayName": display_name,
                    "pieceName": piece_name,
                    "projectId": project_id,
                    # The host's schema wants the discriminator in both
                    # positions: the body's type and inside value.
                    "type": connection_type,
                    "value": {**value, "type": connection_type},
                },
                headers={"Authorization": f"Bearer {session_token}"},
            )
            if response.status_code not in (200, 201):
                raise _step_error("iPaaS connection upsert", response)
            return response.json()

    async def _piece_oauth_metadata(
        self, http: httpx.AsyncClient, headers: dict[str, str], piece_name: str
    ) -> dict[str, Any]:
        """The piece's OAuth auth metadata (scope list), or a clear refusal."""
        response = await http.get(
            f"{self.url}/api/v1/pieces/{piece_name}", headers=headers
        )
        if response.status_code != 200:
            raise _step_error("iPaaS piece lookup", response)
        auth = response.json().get("auth") or {}
        # A piece may declare several auth options; pick the OAuth one.
        if isinstance(auth, list):
            auth = next((a for a in auth if a.get("type") == "OAUTH2"), {})
        if auth.get("type") != "OAUTH2":
            raise IpaasGatewayError(
                f"iPaaS piece '{piece_name}' does not use an OAuth connection; "
                "create it with a token-based connection type instead."
            )
        return auth

    async def _deployment_oauth_client_id(
        self, http: httpx.AsyncClient, headers: dict[str, str], piece_name: str
    ) -> str:
        """The deployment-configured OAuth client id for the piece.

        The listing has no piece filter, so pages are walked until the piece
        is found — the not-configured error below is definitive, never a
        pagination artifact.
        """
        params: dict[str, Any] = {"limit": 100}
        while True:
            response = await http.get(
                f"{self.url}/api/v1/oauth-apps", params=params, headers=headers
            )
            if response.status_code != 200:
                raise _step_error("iPaaS OAuth client lookup", response)
            page = response.json()
            for entry in page.get("data", []):
                if entry.get("pieceName") == piece_name:
                    return entry["clientId"]
            cursor = page.get("next")
            if not cursor:
                raise IpaasGatewayError(
                    f"No OAuth client is configured for piece '{piece_name}' "
                    "on the iPaaS host. Use a token-based connection type for "
                    "this piece, or connect it once via the product UI."
                )
            params["cursor"] = cursor

    async def _authed_mcp_request(
        self,
        advanced_automations_token: str,
        method: str,
        params: dict[str, Any],
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """One self-contained chain: fresh client, auth, then the MCP request."""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
        ) as http:
            access_token = await self._access_token(http, advanced_automations_token)
            return await self._mcp_request(
                http, access_token, method, params, timeout_seconds
            )

    async def _access_token(
        self, http: httpx.AsyncClient, advanced_automations_token: str
    ) -> str:
        """The full auth chain: pipe token -> session -> headless OAuth token.

        The one seam a replica-local token cache would wrap if per-call chain
        cost ever matters; callers only ever see an access token.
        """
        session_token, project_id = await self._exchange_session(
            http, advanced_automations_token
        )
        return await self._oauth_access_token(http, session_token, project_id)

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
        payload = response.json()
        return payload["token"], payload["projectId"]

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
        code = _query_param(response.json().get("redirectUrl", ""), "code")
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
        return response.json()["access_token"]

    async def _mcp_request(
        self,
        http: httpx.AsyncClient,
        access_token: str,
        method: str,
        params: dict[str, Any],
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """MCP handshake against the iPaaS endpoint; return the JSON-RPC result."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            # The endpoint may answer plain JSON or a single SSE event.
            "Accept": "application/json, text/event-stream",
        }
        mcp_url = f"{self.url}/mcp"
        try:
            # The endpoint is stateless (no session id); initialize is
            # informational but keeps us honest with clients that enforce the
            # MCP lifecycle.
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
        except httpx.TimeoutException as exc:
            # Distinct from the invocation timeout below: nothing has been
            # executed yet, so retrying is the right move, not run inspection.
            raise IpaasGatewayError(
                "iPaaS MCP handshake timed out; the host is slow or briefly "
                "unavailable — nothing was executed, so it is safe to retry."
            ) from exc
        try:
            response = await http.post(
                mcp_url,
                json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
                headers=headers,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise IpaasGatewayError(
                f"iPaaS {method} timed out after {timeout_seconds:.0f}s; a "
                "long-running tool may still be executing on the iPaaS host — "
                "inspect progress with the run-listing tools instead of retrying."
            ) from exc
        if response.status_code != 200:
            raise _step_error(f"iPaaS {method}", response)
        payload = _parse_mcp_response(response)
        if "error" in payload:
            raise IpaasGatewayError(
                f"iPaaS {method} returned an error: {payload['error']}"
            )
        if "result" not in payload:
            raise IpaasGatewayError(
                f"iPaaS {method} returned a response with no result."
            )
        return payload["result"]


def oauth_connection_value(
    completion: dict[str, Any], code: str
) -> tuple[str, dict[str, Any]]:
    """The upsert ``(type, value)`` for an OAuth connection from its bundle.

    Lives in the gateway because it is wire-format knowledge: the field names
    (including the quirk that ``code_challenge`` carries the PKCE *verifier*)
    must stay in lockstep with :meth:`IpaasGateway.connection_auth_url`, which
    mints the bundle this consumes.

    Raises:
        ValueError: When the bundle is missing required fields (i.e. it was
            not passed back verbatim).
    """
    missing = [
        key for key in ("type", "client_id", "redirect_url") if key not in completion
    ]
    if missing:
        raise ValueError(
            f"oauth.completion is missing {', '.join(missing)}; pass back the "
            "bundle from get_ipaas_connection_auth_url verbatim."
        )
    value: dict[str, Any] = {
        "client_id": completion["client_id"],
        "code": code,
        "scope": completion.get("scope", ""),
        "redirect_url": completion["redirect_url"],
    }
    if completion.get("code_verifier"):
        # The wire field is named code_challenge but carries the verifier.
        value["code_challenge"] = completion["code_verifier"]
    return completion["type"], value


def _query_param(url: str, name: str) -> str | None:
    values = parse_qs(urlparse(url).query).get(name)
    return values[0] if values else None


def _parse_mcp_response(response: httpx.Response) -> dict[str, Any]:
    """Decode a JSON-RPC response that may arrive as JSON or SSE events.

    Today the host answers one data event per request, but the stream may
    also carry notification frames (no ``result``/``error``) ahead of the
    response on future host versions, so the response frame is selected
    rather than assumed first.
    """
    if "text/event-stream" not in response.headers.get("content-type", ""):
        return response.json()
    frames = [
        json.loads(line[len("data:") :].strip())
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]
    for frame in frames:
        if "result" in frame or "error" in frame:
            return frame
    if frames:
        return frames[-1]
    raise IpaasGatewayError(
        "iPaaS MCP endpoint returned an event stream with no data event."
    )


__all__ = ["IpaasGateway", "IpaasGatewayError", "oauth_connection_value"]
