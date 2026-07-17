"""MCP tools for pipe-scoped AI knowledge bases (list, plain text CRUD, probe).

Reads and writes reach the API with the request-scoped credential and are fully
governed by API permissions. Writes are gated on the caller running
``validate_knowledge_base_access`` first (explicit-validate-first): the tools do
not auto-probe inside create/update. Deletes require a two-step confirm.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pipefy_sdk import classify_exception

from pipefy_mcp.core.tool_error_envelope import (
    is_unified_envelope_enabled,
    tool_error,
    tool_success,
)
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.tool_context import get_pipefy_client

_KB_ID_DISCOVERY_HINT = (
    "Use 'get_ai_knowledge_bases' to list knowledge base IDs for the pipe."
)


def _kb_tool_error_from_exception(exc: BaseException) -> dict[str, Any]:
    """Map an SDK/GraphQL exception onto the canonical tool failure envelope.

    Uses the shared SDK classifier so the kind/code the CLI and probe see is the
    same reported here. A transport-level failure with no GraphQL errors falls
    back to ``str(exc)``.
    """
    problem = classify_exception(exc)
    if problem is None:
        return tool_error(str(exc))
    message = problem.message
    if problem.kind.value == "not_found":
        message = f"{message} {_KB_ID_DISCOVERY_HINT}"
    details: dict[str, Any] = {"kind": problem.kind.value}
    if problem.correlation_id:
        details["correlation_id"] = problem.correlation_id
    return tool_error(message, code=problem.code, details=details)


def _blank_error(value: str, field: str) -> dict[str, Any] | None:
    if not value.strip():
        return tool_error(f"'{field}' must be non-empty.")
    return None


def _kb_success(data: dict[str, Any], *, message: str) -> dict[str, Any]:
    """Unified-envelope success (legacy flat payload when the flag is off)."""
    if is_unified_envelope_enabled():
        return tool_success(data=data, message=message)
    return {"success": True, **data}


class KnowledgeBaseTools:
    """Declares MCP tools for pipe-scoped AI knowledge bases."""

    @staticmethod
    def register(mcp: FastMCP) -> None:
        """Register knowledge base tools on the MCP server."""

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
        async def get_ai_knowledge_bases(
            ctx: Context,
            pipe_uuid: str,
        ) -> dict[str, Any]:
            """List every knowledge base item on a pipe: plain texts, documents, and data lookups in one surface. Use this to discover the `dataSourceIds` values an AI agent or behavior can attach.

            Each item carries `id` (the data-source ID used in `dataSourceIds`),
            `type` (e.g. `knowledge_base_plain_texts`), `name`, `description`, and
            `updatedAt`. There is no pagination; the full list is returned.

            Args:
                pipe_uuid: Pipe UUID (not the numeric ID; `get_pipe` returns the `uuid` field).
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(pipe_uuid, "pipe_uuid")
            if err is not None:
                return err
            try:
                items = await client.get_ai_knowledge_bases(pipe_uuid.strip())
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            return _kb_success(
                {"knowledge_bases": items}, message="Knowledge bases retrieved."
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
        async def get_ai_knowledge_base_plain_text(
            ctx: Context,
            plain_text_id: str,
            pipe_uuid: str,
        ) -> dict[str, Any]:
            """Fetch one pipe-scoped knowledge base plain text by ID, including its full content.

            Args:
                plain_text_id: Knowledge base plain text ID (from `get_ai_knowledge_bases`).
                pipe_uuid: Pipe UUID (not the numeric ID).
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(plain_text_id, "plain_text_id") or _blank_error(
                pipe_uuid, "pipe_uuid"
            )
            if err is not None:
                return err
            try:
                plain_text = await client.get_ai_knowledge_base_plain_text(
                    plain_text_id.strip(), pipe_uuid.strip()
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            if not plain_text:
                return tool_error(
                    f"Knowledge base plain text not found: {plain_text_id.strip()}. "
                    f"{_KB_ID_DISCOVERY_HINT}"
                )
            return _kb_success(
                {"knowledge_base_plain_text": plain_text},
                message="Knowledge base plain text retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
        )
        async def create_ai_knowledge_base_plain_text(
            ctx: Context,
            pipe_uuid: str,
            name: str,
            content: str,
            description: str,
        ) -> dict[str, Any]:
            """Create a pipe-scoped knowledge base plain text. Requires manage_ai_agents on the pipe; run `validate_knowledge_base_access` first to confirm access.

            Limits are enforced client-side to fail fast: `content` is 1-3500
            characters and `description` is 1-900 characters (both required). To
            attach the result to an agent, pass the returned `id` in the agent's or
            behavior's `dataSourceIds`.

            Args:
                pipe_uuid: Pipe UUID (not the numeric ID).
                name: Display name (required, non-blank).
                content: Plain text content (required, 1-3500 characters).
                description: Description (required, 1-900 characters).
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(pipe_uuid, "pipe_uuid")
            if err is not None:
                return err
            try:
                plain_text = await client.create_ai_knowledge_base_plain_text(
                    pipe_uuid.strip(),
                    name=name,
                    content=content,
                    description=description,
                )
            except ValueError as exc:
                return tool_error(str(exc))
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            return _kb_success(
                {"knowledge_base_plain_text": plain_text},
                message="Knowledge base plain text created.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
        )
        async def update_ai_knowledge_base_plain_text(
            ctx: Context,
            plain_text_id: str,
            pipe_uuid: str,
            name: str | None = None,
            content: str | None = None,
            description: str | None = None,
        ) -> dict[str, Any]:
            """Update a pipe-scoped knowledge base plain text. Requires manage_ai_agents; run `validate_knowledge_base_access` first.

            Partial update: only the fields you pass change; omitted fields keep
            their stored value. Provide at least one of `name`, `content`, or
            `description`. When given, `content` is 1-3500 characters and
            `description` is 1-900 characters (limits enforced client-side).

            Args:
                plain_text_id: Plain text ID to update (from `get_ai_knowledge_bases`).
                pipe_uuid: Pipe UUID (not the numeric ID).
                name: New name (non-blank when given).
                content: New content (1-3500 characters when given).
                description: New description (1-900 characters when given).
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(plain_text_id, "plain_text_id") or _blank_error(
                pipe_uuid, "pipe_uuid"
            )
            if err is not None:
                return err
            try:
                plain_text = await client.update_ai_knowledge_base_plain_text(
                    plain_text_id.strip(),
                    pipe_uuid.strip(),
                    name=name,
                    content=content,
                    description=description,
                )
            except ValueError as exc:
                return tool_error(str(exc))
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            return _kb_success(
                {"knowledge_base_plain_text": plain_text},
                message="Knowledge base plain text updated.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
        )
        async def delete_ai_knowledge_base_plain_text(
            ctx: Context,
            plain_text_id: str,
            pipe_uuid: str,
            confirm: bool = False,
        ) -> dict[str, Any]:
            """Delete a pipe-scoped knowledge base plain text permanently. This action is irreversible.

            Two-step operation: preview with `confirm=False` (default), then execute
            with `confirm=True` after explicit human approval. Elicitation does not
            authorize deletion (only `confirm=True` does). Requires manage_ai_agents
            on the pipe.

            Args:
                plain_text_id: Plain text ID to delete (from `get_ai_knowledge_bases`).
                pipe_uuid: Pipe UUID (not the numeric ID).
                confirm: Must be `True` to run the delete mutation.
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(plain_text_id, "plain_text_id") or _blank_error(
                pipe_uuid, "pipe_uuid"
            )
            if err is not None:
                return err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=(
                    f"knowledge base plain text (ID: {plain_text_id.strip()})"
                ),
            )
            if guard is not None:
                return guard

            try:
                result = await client.delete_ai_knowledge_base_plain_text(
                    plain_text_id.strip(), pipe_uuid.strip()
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            if not result.get("success"):
                errs = result.get("errors") or []
                detail = (
                    "; ".join(str(e) for e in errs)
                    if errs
                    else "API returned success=false"
                )
                return tool_error(
                    f"delete_ai_knowledge_base_plain_text failed: {detail}"
                )
            return _kb_success(
                {"deleted_id": plain_text_id.strip()},
                message="Knowledge base plain text deleted.",
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
        async def validate_knowledge_base_access(
            ctx: Context,
            pipe_uuid: str,
        ) -> dict[str, Any]:
            """Probe whether the current credential can read a pipe's knowledge bases. A green result proves READ access only (read_ai_agents), never the manage_ai_agents entitlement plain-text create/update/delete require.

            On success, reports how many knowledge base items are visible. On a
            classified failure, returns the structured problem (permission denied /
            not found / invalid arguments) instead of an opaque error. Run this
            before knowledge base writes to confirm access.

            Args:
                pipe_uuid: Pipe UUID (not the numeric ID).
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(pipe_uuid, "pipe_uuid")
            if err is not None:
                return err
            try:
                probe = await client.validate_knowledge_base_access(pipe_uuid.strip())
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            if probe.get("ok"):
                return _kb_success(
                    dict(probe), message="Knowledge base read access confirmed."
                )
            problem = probe.get("problem") or {}
            return tool_error(
                str(problem.get("message") or "Knowledge base access probe failed."),
                code=problem.get("code"),
                details={
                    k: v
                    for k, v in (
                        ("kind", problem.get("kind")),
                        ("correlation_id", problem.get("correlation_id")),
                    )
                    if v
                },
            )
