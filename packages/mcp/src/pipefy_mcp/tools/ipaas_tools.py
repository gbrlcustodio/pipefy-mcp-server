"""MCP tools for the iPaaS (Advanced Automations) tool surface."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import unquote

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pipefy_sdk import PipefyId

from pipefy_mcp.core.ipaas_gateway import IpaasGateway, oauth_connection_value
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import ensure_non_empty_error_message
from pipefy_mcp.tools.introspection_tool_helpers import (
    build_error_payload,
    build_success_payload,
)
from pipefy_mcp.tools.remote_profile import REMOTE
from pipefy_mcp.tools.tool_context import (
    get_ipaas_gateway,
    get_pipefy_client,
    is_remote_profile,
)

_NOT_CONFIGURED_MESSAGE = (
    "The iPaaS tools are disabled on this server (PIPEFY_IPAAS_OAUTH_CLIENT_ID "
    "is blank). Restore the default or set a client id to enable them."
)

_IPAAS_REQUEST_FAILED = (
    "iPaaS request failed. If this was a write, re-read counts/ids "
    "before retrying; do not blind-retry."
)

# Only variables under this prefix are resolvable through {"$env": ...}
# references, so the tool cannot be steered into shipping unrelated process
# secrets to a workspace as a "connection".
_ENV_REF_PREFIX = "PIPEFY_IPAAS_CONNECTION_"

_SECRET_CONNECTION_TYPES = ("SECRET_TEXT", "BASIC_AUTH", "CUSTOM_AUTH")

IPAAS_DESTRUCTIVE_NEEDLES = (
    "delete",
    "remove",
    "destroy",
    "drop",
    "uninstall",
    "revoke",
)


def ipaas_call_is_destructive(
    entry: dict[str, Any], arguments: dict[str, Any] | None
) -> bool:
    """Whether a catalog call must take the two-step confirmation ticket.

    Order (do not reorder): annotation true; ``operation`` needle-equality;
    annotation false stops; else ``tool_name`` substring needles. ``entry`` is
    the raw ``list_tools`` wire object; a missing catalog name is passed as
    ``{"name": tool_name}`` (treated as no boolean).
    """
    hint = _catalog_destructive_hint(entry)
    if hint is True:
        return True
    if _operation_equals_destructive_needle(arguments):
        return True
    if hint is False:
        return False
    name = _catalog_tool_name(entry)
    folded = name.casefold()
    return any(needle in folded for needle in IPAAS_DESTRUCTIVE_NEEDLES)


def _catalog_destructive_hint(entry: dict[str, Any]) -> bool | None:
    annotations = entry.get("annotations")
    if not isinstance(annotations, dict):
        return None
    hint = annotations.get("destructiveHint")
    return hint if isinstance(hint, bool) else None


def _catalog_tool_name(entry: dict[str, Any]) -> str:
    name = entry.get("name")
    return name if isinstance(name, str) else ""


def _operation_equals_destructive_needle(arguments: dict[str, Any] | None) -> bool:
    if arguments is None or "operation" not in arguments:
        return False
    value = arguments["operation"]
    if not isinstance(value, str):
        return False
    return value.casefold() in IPAAS_DESTRUCTIVE_NEEDLES


def _arguments_digest(arguments: dict[str, Any] | None) -> str:
    canonical: dict[str, Any] = dict(arguments or {})
    if "operation" in canonical and isinstance(canonical["operation"], str):
        canonical["operation"] = canonical["operation"].casefold()
    return hashlib.sha256(
        json.dumps(
            canonical, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
    ).hexdigest()


def _ipaas_call_resource_identity(
    pipe_id: PipefyId, tool_name: str, arguments: dict[str, Any] | None
) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "pipe_id": str(pipe_id),
        "tool_name": tool_name,
        "arguments": _arguments_digest(arguments),
    }
    if arguments is not None and "operation" in arguments:
        identity["operation"] = str(arguments["operation"]).casefold()
    return identity


def _ipaas_call_resource_descriptor(
    pipe_id: PipefyId, tool_name: str, arguments: dict[str, Any] | None
) -> str:
    descriptor = f"iPaaS catalog tool '{tool_name}' on pipe {pipe_id}"
    if not arguments:
        return descriptor
    rendered = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    return f"{descriptor} ({rendered})"


def _catalog_entry_named(
    tools: list[dict[str, Any]], tool_name: str
) -> dict[str, Any] | None:
    for tool in tools:
        if tool.get("name") == tool_name:
            return tool
    return None


def _first_line(text: str | None) -> str:
    stripped = (text or "").strip()
    return stripped.splitlines()[0] if stripped else ""


async def _run_ipaas_tool(
    ctx: Context,
    pipe_id: PipefyId,
    work: Callable[[IpaasGateway, str], Awaitable[dict]],
) -> dict:
    """The iPaaS tools' shared preamble and error contract.

    Resolves the gateway (reporting the capability disabled when
    unconfigured), opens the caller's client, mints the pipe token, and maps
    any failure onto the standard error payload. ``work(gateway, token)``
    supplies the tool-specific call and its success payload.
    """
    gateway = get_ipaas_gateway(ctx)
    if gateway is None:
        return build_error_payload(_NOT_CONFIGURED_MESSAGE)

    client = get_pipefy_client(ctx)
    try:
        token = await client.get_advanced_automations_token(pipe_id)
        return await work(gateway, token)
    except Exception as exc:  # noqa: BLE001
        return build_error_payload(
            ensure_non_empty_error_message(str(exc), _IPAAS_REQUEST_FAILED)
        )


class IpaasTools:
    """Registers MCP tools for iPaaS (Advanced Automations) operations."""

    @staticmethod
    def register(mcp: MCPServer) -> None:
        """Register iPaaS-related tools on the MCP server."""

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
            meta=REMOTE,
        )
        async def get_ipaas_tools(
            pipe_id: PipefyId,
            ctx: Context,
            tool_name: str | None = None,
        ) -> dict:
            """List the iPaaS (Advanced Automations) tools available for a pipe.

            iPaaS is Pipefy's embedded workflow-automation platform; each pipe
            has its own iPaaS workspace with a large tool catalog (flow
            building, testing, tables, runs). This meta tool exposes that
            catalog lazily: by default it returns a compact ``name`` +
            one-line ``description`` list, and with ``tool_name`` it returns
            that single tool's full description and input schema. Call it
            without ``tool_name`` to discover what is available, then drill
            into one tool right before using it — never load every schema.

            Requires permission to create automations on the pipe and iPaaS
            enabled on the organization.

            Args:
                pipe_id: Numeric pipe ID whose iPaaS workspace to inspect.
                tool_name: Exact tool name to expand. Omit for the compact
                    catalog.
            """

            async def work(gateway: IpaasGateway, token: str) -> dict:
                tools = await gateway.list_tools(token)
                if tool_name is not None:
                    return _single_tool_payload(tools, tool_name)
                catalog = [
                    {
                        "name": tool.get("name", ""),
                        "description": _first_line(tool.get("description")),
                    }
                    for tool in tools
                ]
                return build_success_payload(
                    {
                        "pipe_id": str(pipe_id),
                        "count": len(catalog),
                        "tools": catalog,
                        "hint": (
                            "Call get_ipaas_tools again with tool_name=<name> "
                            "for a tool's full description and input schema, "
                            "then run it with call_ipaas_tool(pipe_id, "
                            "tool_name=<name>, arguments={...})."
                        ),
                    }
                )

            return await _run_ipaas_tool(ctx, pipe_id, work)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=True, openWorldHint=True
            ),
            meta=REMOTE,
        )
        async def call_ipaas_tool(
            pipe_id: PipefyId,
            tool_name: str,
            ctx: Context,
            arguments: dict[str, Any] | None = None,
            confirm: bool = False,
            confirmation_token: str | None = None,
        ) -> dict:
            """Invoke one iPaaS (Advanced Automations) tool in a pipe's workspace.

            The counterpart of ``get_ipaas_tools``: that tool discovers what is
            callable, this one calls it. Always drill into the tool first
            (``get_ipaas_tools`` with ``tool_name``) and build ``arguments``
            from its input schema — the iPaaS host validates them and its
            error messages are returned here verbatim.

            Destructive catalog calls need a preview token: annotation
            ``true``, or ``arguments.operation`` equal to a delete-like needle
            (case-insensitive equality), else a delete-like substring in the
            catalog name. Call once to receive ``confirmation_token``, then
            echo that token with ``confirm=True`` on step 2. Mixed manage
            ADD/UPDATE stay one-shot unless a confirmation token is supplied.
            A token is replayable within its TTL.

            Prefer the read and validate tools while iterating, and for
            long-running executions (flow tests, retries) inspect progress
            with the run-listing tools rather than re-invoking.

            Requires permission to create automations on the pipe and iPaaS
            enabled on the organization.

            Args:
                pipe_id: Numeric pipe ID whose iPaaS workspace to act on.
                tool_name: Exact tool name from the ``get_ipaas_tools``
                    catalog.
                arguments: Arguments matching the tool's input schema. Omit
                    for tools that take none.
                confirm: Set to True with the preview token to run a
                    destructive catalog call (step 2).
                confirmation_token: Token from the preview response; echo it
                    on step 2.
            """

            async def work(gateway: IpaasGateway, token: str) -> dict:
                async with gateway.mcp_session(token) as ipaas_session:
                    catalog = await ipaas_session.list_tools()
                    entry = _catalog_entry_named(catalog, tool_name)
                    judged = {"name": tool_name} if entry is None else entry
                    destructive = ipaas_call_is_destructive(judged, arguments)
                    # A leftover DELETE token must not authorize mixed ADD
                    # (identity includes operation). ADD without a token stays
                    # one-shot.
                    if destructive or confirmation_token:
                        descriptor = _ipaas_call_resource_descriptor(
                            pipe_id, tool_name, arguments
                        )
                        if destructive:
                            irreversible = (
                                f"⚠️ Running {descriptor} is permanent "
                                "and cannot be undone."
                            )
                        else:
                            irreversible = (
                                f"⚠️ Running {descriptor} is being "
                                "re-checked against its confirmation token."
                            )
                        guard = await check_destructive_confirmation(
                            ctx,
                            confirm=confirm,
                            resource_descriptor=descriptor,
                            irreversible_sentence=irreversible,
                            resource_identity=_ipaas_call_resource_identity(
                                pipe_id, tool_name, arguments
                            ),
                            tool_name="call_ipaas_tool",
                            confirmation_token=confirmation_token,
                        )
                        if guard is not None:
                            return guard
                    result = await ipaas_session.call_tool(tool_name, arguments)
                return _call_result_payload(pipe_id, tool_name, result)

            return await _run_ipaas_tool(ctx, pipe_id, work)

        # Not read-only despite fetching a URL: each call POSTs for a fresh,
        # single-use PKCE bundle (code_verifier), so a hosted client must not
        # treat it as a cacheable pure read and replay a stale verifier.
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=True),
            meta=REMOTE,
        )
        async def get_ipaas_connection_auth_url(
            pipe_id: PipefyId,
            piece_name: str,
            ctx: Context,
        ) -> dict:
            """Step 1 of connecting an OAuth-based app to a pipe's iPaaS workspace.

            Returns an ``authorization_url`` the user must open in a browser to
            grant consent, plus a ``completion`` bundle. Send the URL to the
            user; after they authorize, they land on a page that keeps the
            redirect URL (containing ``?code=...``) in the address bar — ask
            them to paste that full URL back. Then call
            ``create_ipaas_connection`` with ``oauth={"completion": <the bundle,
            verbatim>, "authorization_response": "<what the user pasted>"}``.

            The bundle is single-use and short-lived; nothing is stored between
            the two steps. For pieces that use a token or API key instead of
            OAuth, skip this tool and call ``create_ipaas_connection`` directly.

            Args:
                pipe_id: Numeric pipe ID whose iPaaS workspace to connect.
                piece_name: Exact piece name (as returned by the catalog's
                    piece-research tools).
            """

            async def work(gateway: IpaasGateway, token: str) -> dict:
                result = await gateway.connection_auth_url(token, piece_name)
                return build_success_payload(
                    {
                        "pipe_id": str(pipe_id),
                        "piece_name": piece_name,
                        **result,
                        "instructions": (
                            "Have the user open authorization_url and "
                            "authorize. They will land on a page whose address "
                            "bar holds the redirect URL with ?code=...; ask "
                            "them to paste that full URL back, then call "
                            "create_ipaas_connection with oauth={completion, "
                            "authorization_response}."
                        ),
                    }
                )

            return await _run_ipaas_tool(ctx, pipe_id, work)

        @mcp.tool(annotations=ToolAnnotations(openWorldHint=True), meta=REMOTE)
        async def create_ipaas_connection(
            pipe_id: PipefyId,
            piece_name: str,
            ctx: Context,
            connection_type: str | None = None,
            value: dict[str, Any] | None = None,
            oauth: dict[str, Any] | None = None,
            display_name: str | None = None,
            external_id: str | None = None,
        ) -> dict:
            """Create a connection (app credential) in a pipe's iPaaS workspace.

            Before creating, list existing connections (the catalog's
            connection-listing tool): if one already serves the piece, prefer
            reusing it — and when several candidates exist, name them and ask
            the user which to use instead of picking silently.

            Two modes:

            * **Token/API-key pieces** — pass ``connection_type`` (one of
              ``SECRET_TEXT``, ``BASIC_AUTH``, ``CUSTOM_AUTH``) and ``value``
              matching the piece's auth props (e.g. ``{"secret_text": "..."}``,
              or ``{"props": {...}}`` for ``CUSTOM_AUTH``). A secret given as a
              literal transits the conversation (and therefore the model
              vendor) — tell the user this when asking for a credential. To
              keep the secret out of the conversation entirely, the user can
              store it in the MCP server's environment and reference it as
              ``{"$env": "PIPEFY_IPAAS_CONNECTION_<NAME>"}`` anywhere a string
              is expected (requires the variable to be set before the server
              starts; locally-run servers only — the hosted server rejects
              env references, since its environment is shared by every
              caller). Never repeat a provided secret back in any reply.
            * **OAuth pieces** — first call ``get_ipaas_connection_auth_url``;
              then pass ``oauth={"completion": <bundle, verbatim>,
              "authorization_response": "<pasted redirect URL or bare code>"}``.

            Creation is an upsert keyed on ``external_id``: omit it to create a
            new connection under a generated id; pass an existing connection's
            ``external_id`` only to rotate that connection's credential in
            place. The iPaaS host validates credentials on creation, so a bad
            token fails here, not at the first flow run.

            Requires permission to create automations on the pipe and iPaaS
            enabled on the organization.

            Args:
                pipe_id: Numeric pipe ID whose iPaaS workspace to connect.
                piece_name: Exact piece name the connection is for.
                connection_type: Token-mode auth type; omit in OAuth mode.
                value: Token-mode auth props; omit in OAuth mode.
                oauth: OAuth-mode payload; omit in token mode.
                display_name: Human-readable name shown in the workspace.
                external_id: Existing connection id to rotate; omit to create.
            """

            async def work(gateway: IpaasGateway, token: str) -> dict:
                upsert_type, upsert_value = _connection_request(
                    connection_type,
                    value,
                    oauth,
                    env_refs_allowed=not is_remote_profile(ctx),
                )
                connection_id = external_id or f"mcp-{uuid.uuid4().hex[:12]}"
                connection = await gateway.upsert_connection(
                    token,
                    piece_name=piece_name,
                    connection_type=upsert_type,
                    value=upsert_value,
                    external_id=connection_id,
                    display_name=display_name or connection_id,
                )
                # Relay only non-sensitive fields; the create response is not
                # guaranteed to be credential-free.
                return build_success_payload(
                    {
                        "pipe_id": str(pipe_id),
                        "connection": {
                            key: connection.get(key)
                            for key in (
                                "id",
                                "externalId",
                                "displayName",
                                "pieceName",
                                "status",
                                "type",
                            )
                        },
                        "hint": (
                            "Reference this connection from flow steps by its "
                            "externalId."
                        ),
                    }
                )

            return await _run_ipaas_tool(ctx, pipe_id, work)


def _connection_request(
    connection_type: str | None,
    value: dict[str, Any] | None,
    oauth: dict[str, Any] | None,
    *,
    env_refs_allowed: bool,
) -> tuple[str, dict[str, Any]]:
    """Normalize the tool's two modes into an upsert (type, value) pair."""
    if oauth is not None:
        if connection_type is not None or value is not None:
            raise ValueError("Pass either oauth or connection_type/value, not both.")
        completion = oauth.get("completion")
        if not isinstance(completion, dict):
            raise ValueError(
                "oauth.completion must be the bundle returned by "
                "get_ipaas_connection_auth_url, passed back verbatim."
            )
        code = _extract_authorization_code(
            str(oauth.get("authorization_response") or "")
        )
        return oauth_connection_value(completion, code)
    if connection_type not in _SECRET_CONNECTION_TYPES:
        raise ValueError(
            "connection_type must be one of "
            f"{', '.join(_SECRET_CONNECTION_TYPES)} (or pass oauth for OAuth "
            "pieces, after get_ipaas_connection_auth_url)."
        )
    if not isinstance(value, dict) or not value:
        raise ValueError(
            "value must be a non-empty object matching the piece's auth props."
        )
    return connection_type, _resolve_env_refs(value, allowed=env_refs_allowed)


def _extract_authorization_code(authorization_response: str) -> str:
    """Accept the full pasted redirect URL or a bare authorization code."""
    stripped = authorization_response.strip()
    if not stripped:
        raise ValueError(
            "oauth.authorization_response is empty; paste the full redirect "
            "URL (containing ?code=...) or the bare code."
        )
    if "?" in stripped or "://" in stripped:
        # Pull the raw value rather than form-decode the query: form decoding
        # would turn an unencoded '+' inside the code into a space.
        match = re.search(r"[?&]code=([^&#\s]+)", stripped)
        if match is None:
            raise ValueError(
                "The pasted redirect URL contains no ?code= parameter; make "
                "sure the user copied the URL they landed on after authorizing."
            )
        return unquote(match.group(1))
    return stripped


def _resolve_env_refs(node: Any, *, allowed: bool) -> Any:
    """Resolve {"$env": NAME} references from the server's environment.

    Only variables under the PIPEFY_IPAAS_CONNECTION_ prefix resolve; this is
    the boundary that keeps the tool from exfiltrating unrelated process
    secrets. The semantics are single-user: the environment belongs to one
    local server process. On the hosted ``remote`` profile the environment is
    the deployment's, shared by every caller, so the tool passes
    ``allowed=False`` there and any reference is rejected instead of
    resolved.
    """
    if isinstance(node, dict):
        if "$env" in node:
            if not allowed:
                raise ValueError(
                    '{"$env": ...} references are disabled on the hosted '
                    "server: they resolve from the server's own environment, "
                    "which is shared by every caller. Pass the credential "
                    "value directly, or use the OAuth flow "
                    "(get_ipaas_connection_auth_url) instead."
                )
            if set(node) != {"$env"}:
                raise ValueError(
                    'an {"$env": ...} reference must be an object whose only '
                    'key is "$env"; remove the other keys or nest the '
                    "reference where the string is expected."
                )
            name = node["$env"]
            if not isinstance(name, str) or not name.startswith(_ENV_REF_PREFIX):
                raise ValueError(
                    "$env references must name a variable starting with "
                    f"{_ENV_REF_PREFIX}; got {name!r}."
                )
            resolved = os.environ.get(name)
            if resolved is None:
                raise ValueError(
                    f"Environment variable {name!r} is not set in the MCP "
                    "server process. Add it to the server's environment (e.g. "
                    "the env block of its MCP configuration) and reconnect."
                )
            return resolved
        return {
            key: _resolve_env_refs(item, allowed=allowed) for key, item in node.items()
        }
    if isinstance(node, list):
        return [_resolve_env_refs(item, allowed=allowed) for item in node]
    return node


def _call_result_payload(
    pipe_id: PipefyId, tool_name: str, result: dict[str, Any]
) -> dict:
    """Map a wire-format ``tools/call`` result onto the standard envelope.

    Text content is joined and relayed in full — the result is the
    deliverable, so no trimming. A host-side ``isError`` becomes the standard
    error payload; content types other than text are passed through raw
    rather than dropped.
    """
    content = result.get("content") or []
    text = "\n".join(
        item.get("text", "") for item in content if item.get("type") == "text"
    )
    if result.get("isError"):
        return build_error_payload(
            text or f"iPaaS tool '{tool_name}' reported an error with no message."
        )
    payload: dict[str, Any] = {
        "pipe_id": str(pipe_id),
        "tool_name": tool_name,
        "output": text,
    }
    other = [item for item in content if item.get("type") != "text"]
    if other:
        payload["content"] = other
    return build_success_payload(payload)


def _single_tool_payload(tools: list[dict[str, Any]], tool_name: str) -> dict:
    """Full wire-format entry for one tool, or an error naming the misses."""
    for tool in tools:
        if tool.get("name") == tool_name:
            return build_success_payload({"tool": tool})
    available = ", ".join(sorted(t.get("name", "") for t in tools))
    return build_error_payload(
        f"iPaaS tool '{tool_name}' not found for this pipe. Available: {available}"
    )
