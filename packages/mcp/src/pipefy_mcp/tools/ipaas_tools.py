"""MCP tools for the iPaaS (Advanced Automations) tool surface."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pipefy_sdk import PipefyId

from pipefy_mcp.tools.introspection_tool_helpers import (
    build_error_payload,
    build_success_payload,
)
from pipefy_mcp.tools.tool_context import get_ipaas_gateway, get_pipefy_client

_NOT_CONFIGURED_MESSAGE = (
    "The iPaaS tools are disabled on this server (PIPEFY_IPAAS_OAUTH_CLIENT_ID "
    "is blank). Restore the default or set a client id to enable them."
)


def _first_line(text: str | None) -> str:
    stripped = (text or "").strip()
    return stripped.splitlines()[0] if stripped else ""


class IpaasTools:
    """Registers MCP tools for iPaaS (Advanced Automations) operations."""

    @staticmethod
    def register(mcp: FastMCP) -> None:
        """Register iPaaS-related tools on the MCP server."""

        # Not marked remote-safe yet: the tool itself is per-user clean (the
        # pipe token is minted with the caller's own session), but the iPaaS
        # chain hasn't been reviewed for hosted exposure.
        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
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
            gateway = get_ipaas_gateway(ctx)
            if gateway is None:
                return build_error_payload(_NOT_CONFIGURED_MESSAGE)

            client = get_pipefy_client(ctx)
            try:
                token = await client.get_advanced_automations_token(pipe_id)
                tools = await gateway.list_tools(token)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))

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
                        "Call get_ipaas_tools again with tool_name=<name> for a "
                        "tool's full description and input schema."
                    ),
                }
            )

        # Not marked remote-safe yet, for the same reason as get_ipaas_tools.
        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=True, openWorldHint=True
            )
        )
        async def call_ipaas_tool(
            pipe_id: PipefyId,
            tool_name: str,
            ctx: Context,
            arguments: dict[str, Any] | None = None,
        ) -> dict:
            """Invoke one iPaaS (Advanced Automations) tool in a pipe's workspace.

            The counterpart of ``get_ipaas_tools``: that tool discovers what is
            callable, this one calls it. Always drill into the tool first
            (``get_ipaas_tools`` with ``tool_name``) and build ``arguments``
            from its input schema — the iPaaS host validates them and its
            error messages are returned here verbatim.

            The catalog includes destructive operations (deleting flows,
            tables, or records): only call those on explicit user intent.
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
            """
            gateway = get_ipaas_gateway(ctx)
            if gateway is None:
                return build_error_payload(_NOT_CONFIGURED_MESSAGE)

            client = get_pipefy_client(ctx)
            try:
                token = await client.get_advanced_automations_token(pipe_id)
                result = await gateway.call_tool(token, tool_name, arguments)
            except Exception as exc:  # noqa: BLE001
                return build_error_payload(str(exc))

            return _call_result_payload(pipe_id, tool_name, result)


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
