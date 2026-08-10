"""MCP tools for pipe-scoped AI knowledge bases (list, plain text/document/data lookup CRUD, probe).

Reads and writes reach the API with the request-scoped credential and are fully
governed by API permissions. Writes are gated on the caller running
``validate_knowledge_base_access`` first (explicit-validate-first): the tools do
not auto-probe inside create/update. Deletes require a two-step confirm.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pipefy_sdk import KnowledgeBaseDocumentUploadError, classify_exception

from pipefy_mcp.core.tool_error_envelope import (
    is_unified_envelope_enabled,
    tool_error,
    tool_success,
)
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import ensure_non_empty_error_message
from pipefy_mcp.tools.remote_profile import REMOTE
from pipefy_mcp.tools.tool_context import get_pipefy_client

_KB_ID_DISCOVERY_HINT = (
    "Use 'get_ai_knowledge_bases' to list knowledge base IDs for the pipe."
)

_KB_REQUEST_FAILED = (
    "Knowledge base request failed. Re-read knowledge base state "
    "before retrying; do not blind-retry."
)


def _kb_document_upload_error(
    exc: KnowledgeBaseDocumentUploadError,
) -> dict[str, Any]:
    """Map a step-tagged document upload failure onto the tool failure envelope.

    ``file_read`` and ``s3_upload`` failures carry their own actionable message;
    ``presigned_url``/``kb_create`` failures are GraphQL/transport errors, so the
    shared SDK classifier is used for a clean kind/code (falling back to the raw
    message). ``step`` (and any S3 ``body_snippet``) always rides in ``details``.
    """
    details: dict[str, Any] = {"step": exc.step}
    if exc.step == "file_read":
        message = str(exc.__cause__) if exc.__cause__ else str(exc)
        return tool_error(
            ensure_non_empty_error_message(message, _KB_REQUEST_FAILED),
            details=details,
        )
    if exc.step == "s3_upload":
        if exc.body_snippet:
            details["body_snippet"] = exc.body_snippet
        return tool_error(
            ensure_non_empty_error_message(str(exc), _KB_REQUEST_FAILED),
            details=details,
        )
    problem = classify_exception(exc.__cause__) if exc.__cause__ else None
    if problem is None:
        return tool_error(
            ensure_non_empty_error_message(str(exc), _KB_REQUEST_FAILED),
            details=details,
        )
    details["kind"] = problem.kind.value
    if problem.correlation_id:
        details["correlation_id"] = problem.correlation_id
    return tool_error(
        ensure_non_empty_error_message(problem.message, _KB_REQUEST_FAILED),
        code=problem.code,
        details=details,
    )


def _kb_tool_error_from_exception(
    exc: BaseException, *, not_found_hint: bool = True
) -> dict[str, Any]:
    """Map an SDK/GraphQL exception onto the canonical tool failure envelope.

    Uses the shared SDK classifier so the kind/code the CLI and probe see is the
    same reported here. A transport-level failure with no GraphQL errors falls
    back to ``str(exc)`` (or a stable non-empty fallback when blank).
    ``not_found_hint`` scopes the id-discovery hint to the per-id tools; the
    list tool passes False so its own failure never tells the caller to retry
    the call that just failed.
    """
    problem = classify_exception(exc)
    if problem is None:
        return tool_error(ensure_non_empty_error_message(str(exc), _KB_REQUEST_FAILED))
    message = problem.message
    if not_found_hint and problem.kind.value == "not_found":
        message = f"{message} {_KB_ID_DISCOVERY_HINT}"
    details: dict[str, Any] = {"kind": problem.kind.value}
    if problem.correlation_id:
        details["correlation_id"] = problem.correlation_id
    return tool_error(
        ensure_non_empty_error_message(message, _KB_REQUEST_FAILED),
        code=problem.code,
        details=details,
    )


def _blank_error(value: str, field: str) -> dict[str, Any] | None:
    if not value.strip():
        return tool_error(f"'{field}' must be non-empty.")
    return None


def _kb_delete_failure(tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
    """Failure envelope for a KB delete that returned ``success=false``.

    Shared by every knowledge base kind so the error surface cannot drift.
    """
    errs = result.get("errors") or []
    detail = "; ".join(str(e) for e in errs) if errs else "API returned success=false"
    return tool_error(f"{tool_name} failed: {detail}")


def _kb_success(data: dict[str, Any], *, message: str) -> dict[str, Any]:
    """Unified-envelope success (legacy flat payload when the flag is off)."""
    if is_unified_envelope_enabled():
        return tool_success(data=data, message=message)
    return {"success": True, **data}


class KnowledgeBaseTools:
    """Declares MCP tools for pipe-scoped AI knowledge bases."""

    @staticmethod
    def register(mcp: MCPServer) -> None:
        """Register knowledge base tools on the MCP server."""

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
        async def get_ai_knowledge_bases(
            ctx: Context,
            pipe_uuid: str,
        ) -> dict[str, Any]:
            """List every knowledge base item on a pipe: plain texts, documents, and data lookups in one surface. Use this to discover the `dataSourceIds` values an AI agent or behavior can attach.

            Each item carries `id` (the data-source ID used in `dataSourceIds`),
            `type`, `name`, `description`, and `updatedAt`. The `type` values are
            `knowledge_base_plain_texts`, `knowledge_base_documents`, and
            `data_lookups` (the data lookup discriminator is not prefixed). There
            is no pagination; the full list is returned.

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
                return _kb_tool_error_from_exception(exc, not_found_hint=False)
            return _kb_success(
                {"knowledge_bases": items}, message="Knowledge bases retrieved."
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
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
            meta=REMOTE,
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
                return tool_error(
                    ensure_non_empty_error_message(str(exc), _KB_REQUEST_FAILED)
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            return _kb_success(
                {"knowledge_base_plain_text": plain_text},
                message="Knowledge base plain text created.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
            meta=REMOTE,
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
                return tool_error(
                    ensure_non_empty_error_message(str(exc), _KB_REQUEST_FAILED)
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            return _kb_success(
                {"knowledge_base_plain_text": plain_text},
                message="Knowledge base plain text updated.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
            meta=REMOTE,
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
                return _kb_delete_failure("delete_ai_knowledge_base_plain_text", result)
            return _kb_success(
                {"deleted_id": plain_text_id.strip()},
                message="Knowledge base plain text deleted.",
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
        async def get_ai_knowledge_base_document(
            ctx: Context,
            document_id: str,
            pipe_uuid: str,
        ) -> dict[str, Any]:
            """Fetch one pipe-scoped knowledge base document by ID.

            `content` is the stored document URL (where the PDF was uploaded),
            not the extracted text.

            Args:
                document_id: Knowledge base document ID (from `get_ai_knowledge_bases`).
                pipe_uuid: Pipe UUID (not the numeric ID).
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(document_id, "document_id") or _blank_error(
                pipe_uuid, "pipe_uuid"
            )
            if err is not None:
                return err
            try:
                document = await client.get_ai_knowledge_base_document(
                    document_id.strip(), pipe_uuid.strip()
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            if not document:
                return tool_error(
                    f"Knowledge base document not found: {document_id.strip()}. "
                    f"{_KB_ID_DISCOVERY_HINT}"
                )
            return _kb_success(
                {"knowledge_base_document": document},
                message="Knowledge base document retrieved.",
            )

        # Left unmarked for the remote profile: create reads a local file_path,
        # which has no meaning on a hosted server (mirrors the attachment tools).
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
        )
        async def create_ai_knowledge_base_document(
            ctx: Context,
            pipe_uuid: str,
            name: str,
            description: str,
            file_path: str,
        ) -> dict[str, Any]:
            """Create a pipe-scoped knowledge base document from a local PDF (one-shot upload). Requires manage_ai_agents on the pipe; run `validate_knowledge_base_access` first.

            Reads the local PDF the MCP server (running as the user) can access,
            uploads it via a presigned URL, then registers the document. `~` is
            expanded. Client-side checks fail fast: the file must be a `.pdf`
            (case-insensitive) under 20 MiB, and `description` is 1-900
            characters (required). Indexing is asynchronous: the document may
            not be searchable by agents immediately. To attach it to an agent,
            pass the returned `id` in the agent's or behavior's `dataSourceIds`.

            Args:
                pipe_uuid: Pipe UUID (not the numeric ID).
                name: Display name (required, non-blank).
                description: Description (required, 1-900 characters).
                file_path: Local path to a `.pdf` file. Supports `~` expansion.
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(pipe_uuid, "pipe_uuid") or _blank_error(
                file_path, "file_path"
            )
            if err is not None:
                return err
            try:
                document = await client.create_ai_knowledge_base_document(
                    pipe_uuid.strip(),
                    name=name,
                    description=description,
                    file_path=file_path.strip(),
                )
            except KnowledgeBaseDocumentUploadError as exc:
                return _kb_document_upload_error(exc)
            except ValueError as exc:
                return tool_error(
                    ensure_non_empty_error_message(str(exc), _KB_REQUEST_FAILED)
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            return _kb_success(
                {"knowledge_base_document": document},
                message="Knowledge base document created.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
            meta=REMOTE,
        )
        async def update_ai_knowledge_base_document(
            ctx: Context,
            document_id: str,
            pipe_uuid: str,
            name: str | None = None,
            description: str | None = None,
        ) -> dict[str, Any]:
            """Update a knowledge base document's metadata. Requires manage_ai_agents; run `validate_knowledge_base_access` first.

            Metadata only: `name` and/or `description`; the PDF file cannot be
            replaced. Provide at least one field. When given, `description` is
            1-900 characters (enforced client-side).

            Args:
                document_id: Document ID to update (from `get_ai_knowledge_bases`).
                pipe_uuid: Pipe UUID (not the numeric ID).
                name: New name (non-blank when given).
                description: New description (1-900 characters when given).
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(document_id, "document_id") or _blank_error(
                pipe_uuid, "pipe_uuid"
            )
            if err is not None:
                return err
            try:
                document = await client.update_ai_knowledge_base_document(
                    document_id.strip(),
                    pipe_uuid.strip(),
                    name=name,
                    description=description,
                )
            except ValueError as exc:
                return tool_error(
                    ensure_non_empty_error_message(str(exc), _KB_REQUEST_FAILED)
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            return _kb_success(
                {"knowledge_base_document": document},
                message="Knowledge base document updated.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
            meta=REMOTE,
        )
        async def delete_ai_knowledge_base_document(
            ctx: Context,
            document_id: str,
            pipe_uuid: str,
            confirm: bool = False,
        ) -> dict[str, Any]:
            """Delete a pipe-scoped knowledge base document permanently. This action is irreversible.

            Two-step operation: preview with `confirm=False` (default), then
            execute with `confirm=True` after explicit human approval.
            Elicitation does not authorize deletion (only `confirm=True` does).
            Requires manage_ai_agents on the pipe.

            Args:
                document_id: Document ID to delete (from `get_ai_knowledge_bases`).
                pipe_uuid: Pipe UUID (not the numeric ID).
                confirm: Must be `True` to run the delete mutation.
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(document_id, "document_id") or _blank_error(
                pipe_uuid, "pipe_uuid"
            )
            if err is not None:
                return err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=(
                    f"knowledge base document (ID: {document_id.strip()})"
                ),
            )
            if guard is not None:
                return guard

            try:
                result = await client.delete_ai_knowledge_base_document(
                    document_id.strip(), pipe_uuid.strip()
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            if not result.get("success"):
                return _kb_delete_failure("delete_ai_knowledge_base_document", result)
            return _kb_success(
                {"deleted_id": document_id.strip()},
                message="Knowledge base document deleted.",
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
        async def get_ai_knowledge_base_data_lookup(
            ctx: Context,
            data_lookup_id: str,
            pipe_uuid: str,
        ) -> dict[str, Any]:
            """Fetch one pipe-scoped knowledge base data lookup by ID.

            Returns `name`, `description`, `sourceRepoId`, `searchQuery`, and
            `outputFields` — never `conditions`: the API stores them but does
            not expose them on reads, so keep your lookup definition (including
            conditions) as the client-side source of truth for updates.

            Args:
                data_lookup_id: Knowledge base data lookup ID (from `get_ai_knowledge_bases`).
                pipe_uuid: Pipe UUID (not the numeric ID).
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(data_lookup_id, "data_lookup_id") or _blank_error(
                pipe_uuid, "pipe_uuid"
            )
            if err is not None:
                return err
            try:
                data_lookup = await client.get_ai_knowledge_base_data_lookup(
                    data_lookup_id.strip(), pipe_uuid.strip()
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            if not data_lookup:
                return tool_error(
                    f"Knowledge base data lookup not found: {data_lookup_id.strip()}. "
                    f"{_KB_ID_DISCOVERY_HINT}"
                )
            return _kb_success(
                {"knowledge_base_data_lookup": data_lookup},
                message="Knowledge base data lookup retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
            meta=REMOTE,
        )
        async def create_ai_knowledge_base_data_lookup(
            ctx: Context,
            pipe_uuid: str,
            name: str,
            description: str,
            source_repo_id: str,
            output_fields: list[str],
            conditions: list[dict[str, Any]],
            search_query: str | None = None,
        ) -> dict[str, Any]:
            """Create a pipe-scoped knowledge base data lookup: an agent data source that searches cards in a source pipe by conditions and returns selected fields. Requires manage_ai_agents on the pipe; run `validate_knowledge_base_access` first.

            The definition is validated client-side because the API accepts
            shapes that only break later, when an agent runs the lookup:
            `source_repo_id` must be the numeric pipe ID (not a UUID);
            `output_fields` takes 1-30 field IDs (field slugs plus static
            fields like `id`, `title`, `created_at`); each condition needs
            `field` and `operator` (an opaque backend string, e.g. `"eq"`,
            `"contains"`) and is either static (string `value` required) or
            AI-filled (`usingFillWithAi: true` with `inputName`, `inputType`
            (e.g. `"text"`, `"number"`), and `inputDescription`; no `value`).
            Keep the full definition client-side: reads never return
            `conditions`. To attach the result to an agent, pass the returned
            `id` in the agent's or behavior's `dataSourceIds`.

            Args:
                pipe_uuid: Pipe UUID (not the numeric ID) that owns the lookup.
                name: Display name (required, non-blank).
                description: Description (required, 1-900 characters).
                source_repo_id: Numeric ID of the source pipe to look up data from.
                output_fields: Field IDs whose values matching records return (1-30).
                conditions: Condition objects (at least one), e.g.
                    `{"field": "customer_email", "operator": "eq", "usingFillWithAi": true, "inputName": "Customer email", "inputType": "text", "inputDescription": "The customer's email address"}`.
                search_query: Optional backend-defined search mode marker; leave unset unless you know the backend value you need.
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(pipe_uuid, "pipe_uuid")
            if err is not None:
                return err
            try:
                data_lookup = await client.create_ai_knowledge_base_data_lookup(
                    pipe_uuid.strip(),
                    name=name,
                    description=description,
                    source_repo_id=source_repo_id,
                    output_fields=output_fields,
                    conditions=conditions,
                    search_query=search_query,
                )
            except ValueError as exc:
                return tool_error(
                    ensure_non_empty_error_message(str(exc), _KB_REQUEST_FAILED)
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            return _kb_success(
                {"knowledge_base_data_lookup": data_lookup},
                message="Knowledge base data lookup created.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
            meta=REMOTE,
        )
        async def update_ai_knowledge_base_data_lookup(
            ctx: Context,
            data_lookup_id: str,
            pipe_uuid: str,
            source_repo_id: str,
            output_fields: list[str],
            conditions: list[dict[str, Any]],
            search_query: str | None = None,
            name: str | None = None,
            description: str | None = None,
        ) -> dict[str, Any]:
            """Update a knowledge base data lookup by replacing its full definition. Requires manage_ai_agents; run `validate_knowledge_base_access` first.

            Every update rewrites the whole definition: the API replaces the
            stored definition with exactly what this call carries, so
            `source_repo_id`, `output_fields`, and `conditions` are required
            every time, and omitting `search_query` clears it. Reads never
            return `conditions`, so resend the definition from your own
            client-side copy. Only `name`/`description` are partial (omitted
            means keep the stored value). Field rules match
            `create_ai_knowledge_base_data_lookup`.

            Args:
                data_lookup_id: Data lookup ID to update (from `get_ai_knowledge_bases`).
                pipe_uuid: Pipe UUID (not the numeric ID).
                source_repo_id: Numeric ID of the source pipe (required; omitting it would strip the source from the stored definition).
                output_fields: Field IDs whose values matching records return (1-30).
                conditions: Condition objects (at least one) — the complete set, not a delta.
                search_query: Optional backend-defined search mode marker; omitted means cleared.
                name: New name (non-blank when given).
                description: New description (1-900 characters when given).
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(data_lookup_id, "data_lookup_id") or _blank_error(
                pipe_uuid, "pipe_uuid"
            )
            if err is not None:
                return err
            try:
                data_lookup = await client.update_ai_knowledge_base_data_lookup(
                    data_lookup_id.strip(),
                    pipe_uuid.strip(),
                    source_repo_id=source_repo_id,
                    output_fields=output_fields,
                    conditions=conditions,
                    search_query=search_query,
                    name=name,
                    description=description,
                )
            except ValueError as exc:
                return tool_error(
                    ensure_non_empty_error_message(str(exc), _KB_REQUEST_FAILED)
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            return _kb_success(
                {"knowledge_base_data_lookup": data_lookup},
                message="Knowledge base data lookup updated.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
            meta=REMOTE,
        )
        async def delete_ai_knowledge_base_data_lookup(
            ctx: Context,
            data_lookup_id: str,
            pipe_uuid: str,
            confirm: bool = False,
        ) -> dict[str, Any]:
            """Delete a pipe-scoped knowledge base data lookup permanently. This action is irreversible.

            Two-step operation: preview with `confirm=False` (default), then
            execute with `confirm=True` after explicit human approval.
            Elicitation does not authorize deletion (only `confirm=True` does).
            Requires manage_ai_agents on the pipe.

            Args:
                data_lookup_id: Data lookup ID to delete (from `get_ai_knowledge_bases`).
                pipe_uuid: Pipe UUID (not the numeric ID).
                confirm: Must be `True` to run the delete mutation.
            """
            client = get_pipefy_client(ctx)
            err = _blank_error(data_lookup_id, "data_lookup_id") or _blank_error(
                pipe_uuid, "pipe_uuid"
            )
            if err is not None:
                return err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=(
                    f"knowledge base data lookup (ID: {data_lookup_id.strip()})"
                ),
            )
            if guard is not None:
                return guard

            try:
                result = await client.delete_ai_knowledge_base_data_lookup(
                    data_lookup_id.strip(), pipe_uuid.strip()
                )
            except Exception as exc:  # noqa: BLE001
                return _kb_tool_error_from_exception(exc)
            if not result.get("success"):
                return _kb_delete_failure(
                    "delete_ai_knowledge_base_data_lookup", result
                )
            return _kb_success(
                {"deleted_id": data_lookup_id.strip()},
                message="Knowledge base data lookup deleted.",
            )

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
        async def validate_knowledge_base_access(
            ctx: Context,
            pipe_uuid: str,
        ) -> dict[str, Any]:
            """Probe whether the current credential can read a pipe's knowledge bases. A green result proves READ access only (read_ai_agents), never the manage_ai_agents entitlement knowledge base writes (plain text, document, data lookup) require.

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
