"""Service for pipe-scoped AI knowledge bases: list, plain text/document CRUD, probe.

Client-side limits fail fast before the network call so callers get an
actionable ``ValueError`` instead of a backend 422. The limits mirror the
downstream ``DataSource``/``KnowledgeBasePlainText`` model validations:
``content`` and ``name`` are required and ``content`` is capped at 3500 chars;
``description`` is required (the GraphQL schema marks it optional, but the
backend rejects a blank one) and capped at 900 chars. Updates omit any field the
caller leaves unset, but validate every field they do pass.

Documents are created one-shot from a local PDF: read the file (``.pdf``
extension and 20 MiB cap enforced here, because the backend skips both when the
document arrives as a URL rather than a raw upload), mint a presigned URL,
PUT the bytes, then run the create mutation with the persistent download URL.
Every stage raises :class:`KnowledgeBaseDocumentUploadError` tagged with the
step that failed. The presign and S3 PUT primitives are shared with the
attachment upload pipeline.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pipefy_infra.filesystem import LocalFile, LocalFileError

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.graphql_problem import (
    GraphQLProblem,
    GraphQLProblemKind,
    classify_graphql_error_dicts,
)
from pipefy_sdk.queries.attachment_queries import CREATE_PRESIGNED_URL_MUTATION
from pipefy_sdk.queries.knowledge_base_queries import (
    CREATE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION,
    CREATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION,
    DELETE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION,
    DELETE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION,
    GET_AI_KNOWLEDGE_BASE_DOCUMENT_QUERY,
    GET_AI_KNOWLEDGE_BASE_PLAIN_TEXT_QUERY,
    GET_AI_KNOWLEDGE_BASES_QUERY,
    GET_PIPE_ORGANIZATION_QUERY,
    UPDATE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION,
    UPDATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION,
)
from pipefy_sdk.services.attachment_service import (
    _ALLOWED_UPLOAD_HOST_RE,
    HttpxS3Uploader,
    S3Uploader,
)
from pipefy_sdk.services.types import (
    KnowledgeBaseAccessProbeResult,
    KnowledgeBaseDeleteResult,
    KnowledgeBaseDocumentPayload,
    KnowledgeBaseDocumentUploadError,
    KnowledgeBasePayload,
    KnowledgeBasePlainTextPayload,
)

MAX_PLAIN_TEXT_CONTENT_LENGTH = 3500
MAX_PLAIN_TEXT_DESCRIPTION_LENGTH = 900

# Document policy, enforced client-side because the backend skips PDF/size
# validation when a document arrives as a URL (the only path these tools use).
# The description cap matches the shared ``DataSource`` rule (max 900).
DOCUMENT_PDF_SUFFIX = ".pdf"
MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_DESCRIPTION_LENGTH = 900
DOCUMENT_CONTENT_TYPE = "application/pdf"

_PROBE_READ_ONLY_NOTE = (
    "Read access confirmed. This proves knowledge-base list/read access only "
    "(read_ai_agents on the pipe), never write entitlement; plain-text "
    "create/update/delete require manage_ai_agents and may still be denied."
)


def _require_non_blank(value: str, name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must be a non-empty string")
    return stripped


def _require_bounded(value: str, name: str, max_length: int) -> str:
    """Require a non-blank, length-capped field (content/description on write)."""
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must be a non-empty string")
    if len(stripped) > max_length:
        raise ValueError(
            f"{name} must be at most {max_length} characters (got {len(stripped)})"
        )
    return stripped


def _problem_dict(problem: GraphQLProblem) -> dict[str, Any]:
    """Project a classified problem onto the probe's plain-dict shape."""
    return {
        "kind": problem.kind.value,
        "message": problem.message,
        "code": problem.code,
        "correlation_id": problem.correlation_id,
    }


class KnowledgeBaseService:
    """Pipe-scoped AI knowledge base reads, plain-text/document writes, and the probe."""

    def __init__(
        self,
        *,
        executor: GraphQLExecutor,
        s3_uploader: S3Uploader | None = None,
    ) -> None:
        self._executor = executor
        self._s3_uploader: S3Uploader = s3_uploader or HttpxS3Uploader(
            allowed_host_pattern=_ALLOWED_UPLOAD_HOST_RE
        )

    async def get_ai_knowledge_bases(
        self, pipe_uuid: str
    ) -> list[KnowledgeBasePayload]:
        """List every knowledge base item on a pipe (plain text, docs, lookups).

        Args:
            pipe_uuid: Pipe UUID (not the numeric id).

        Returns:
            The pipe's knowledge base items; empty list when the pipe has none.
        """
        variables = {"pipeUuid": _require_non_blank(pipe_uuid, "pipe_uuid")}
        response = await self._executor.execute_query(
            GET_AI_KNOWLEDGE_BASES_QUERY, variables
        )
        items = response.get("aiKnowledgeBases")
        return list(items) if isinstance(items, list) else []

    async def get_ai_knowledge_base_plain_text(
        self, plain_text_id: str, pipe_uuid: str
    ) -> KnowledgeBasePlainTextPayload:
        """Fetch one pipe-scoped knowledge base plain text by id.

        Args:
            plain_text_id: Knowledge base plain text UUID (from the list).
            pipe_uuid: Pipe UUID (not the numeric id).

        Returns:
            The plain text dict; empty dict when the API resolves nothing.
        """
        variables = {
            "id": _require_non_blank(plain_text_id, "plain_text_id"),
            "pipeUuid": _require_non_blank(pipe_uuid, "pipe_uuid"),
        }
        response = await self._executor.execute_query(
            GET_AI_KNOWLEDGE_BASE_PLAIN_TEXT_QUERY, variables
        )
        plain_text = response.get("aiKnowledgeBasePlainText")
        return plain_text if isinstance(plain_text, dict) else {}

    async def create_ai_knowledge_base_plain_text(
        self,
        pipe_uuid: str,
        *,
        name: str,
        content: str,
        description: str,
    ) -> KnowledgeBasePlainTextPayload:
        """Create a pipe-scoped knowledge base plain text.

        Args:
            pipe_uuid: Pipe UUID (not the numeric id).
            name: Display name (required, non-blank).
            content: Plain text content (required, 1-3500 chars).
            description: Description (required by the backend, 1-900 chars).

        Returns:
            The created plain text dict.
        """
        input_obj = {
            "pipeUuid": _require_non_blank(pipe_uuid, "pipe_uuid"),
            "name": _require_non_blank(name, "name"),
            "content": _require_bounded(
                content, "content", MAX_PLAIN_TEXT_CONTENT_LENGTH
            ),
            "description": _require_bounded(
                description, "description", MAX_PLAIN_TEXT_DESCRIPTION_LENGTH
            ),
        }
        response = await self._executor.execute_query(
            CREATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION, {"input": input_obj}
        )
        return _unwrap_plain_text(response, "createAiKnowledgeBasePlainText")

    async def update_ai_knowledge_base_plain_text(
        self,
        plain_text_id: str,
        pipe_uuid: str,
        *,
        name: str | None = None,
        content: str | None = None,
        description: str | None = None,
    ) -> KnowledgeBasePlainTextPayload:
        """Update a pipe-scoped knowledge base plain text (partial).

        Only the fields you pass are sent; unset fields keep their stored value.
        At least one of ``name``/``content``/``description`` must be provided.

        Args:
            plain_text_id: Plain text UUID to update.
            pipe_uuid: Pipe UUID (not the numeric id).
            name: New name (non-blank when given).
            content: New content (1-3500 chars when given).
            description: New description (1-900 chars when given).

        Returns:
            The updated plain text dict.
        """
        if name is None and content is None and description is None:
            raise ValueError(
                "Provide at least one of name, content, or description to update."
            )
        input_obj: dict[str, Any] = {
            "pipeUuid": _require_non_blank(pipe_uuid, "pipe_uuid"),
            "plainTextId": _require_non_blank(plain_text_id, "plain_text_id"),
        }
        if name is not None:
            input_obj["name"] = _require_non_blank(name, "name")
        if content is not None:
            input_obj["content"] = _require_bounded(
                content, "content", MAX_PLAIN_TEXT_CONTENT_LENGTH
            )
        if description is not None:
            input_obj["description"] = _require_bounded(
                description, "description", MAX_PLAIN_TEXT_DESCRIPTION_LENGTH
            )
        response = await self._executor.execute_query(
            UPDATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION, {"input": input_obj}
        )
        return _unwrap_plain_text(response, "updateAiKnowledgeBasePlainText")

    async def delete_ai_knowledge_base_plain_text(
        self, plain_text_id: str, pipe_uuid: str
    ) -> KnowledgeBaseDeleteResult:
        """Delete a pipe-scoped knowledge base plain text (permanent).

        Args:
            plain_text_id: Plain text UUID to delete.
            pipe_uuid: Pipe UUID (not the numeric id).

        Returns:
            ``success`` and any backend ``errors``.
        """
        input_obj = {
            "pipeUuid": _require_non_blank(pipe_uuid, "pipe_uuid"),
            "plainTextId": _require_non_blank(plain_text_id, "plain_text_id"),
        }
        response = await self._executor.execute_query(
            DELETE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION, {"input": input_obj}
        )
        payload = response.get("deleteAiKnowledgeBasePlainText")
        payload = payload if isinstance(payload, dict) else {}
        errors = payload.get("errors")
        return {
            "success": bool(payload.get("success")),
            "errors": [str(e) for e in errors] if isinstance(errors, list) else [],
        }

    async def get_ai_knowledge_base_document(
        self, document_id: str, pipe_uuid: str
    ) -> KnowledgeBaseDocumentPayload:
        """Fetch one pipe-scoped knowledge base document by id.

        Args:
            document_id: Knowledge base document ID (from the list).
            pipe_uuid: Pipe UUID (not the numeric id).

        Returns:
            The document dict; empty dict when the API resolves nothing.
            ``content`` is the stored document URL, not the extracted text.
        """
        variables = {
            "id": _require_non_blank(document_id, "document_id"),
            "pipeUuid": _require_non_blank(pipe_uuid, "pipe_uuid"),
        }
        response = await self._executor.execute_query(
            GET_AI_KNOWLEDGE_BASE_DOCUMENT_QUERY, variables
        )
        document = response.get("aiKnowledgeBaseDocument")
        return document if isinstance(document, dict) else {}

    async def create_ai_knowledge_base_document(
        self,
        pipe_uuid: str,
        *,
        name: str,
        description: str,
        file_path: str | Path,
    ) -> KnowledgeBaseDocumentPayload:
        """Create a pipe-scoped knowledge base document from a local PDF (one-shot).

        The pipeline reads the local PDF (validating the ``.pdf`` extension and
        the 20 MiB cap client-side, since the backend skips both on the URL
        path), requests a presigned URL for the pipe's organization, PUTs the
        bytes, and runs the create mutation with the persistent download URL.
        Indexing is asynchronous: the document may not be searchable by agents
        immediately after this returns.

        Args:
            pipe_uuid: Pipe UUID (not the numeric id).
            name: Display name (required, non-blank).
            description: Description (required by the backend, 1-900 chars).
            file_path: Local path to a ``.pdf`` file (``~`` is expanded).

        Returns:
            The created document dict.

        Raises:
            ValueError: When ``name``/``description``/``pipe_uuid`` are invalid.
            KnowledgeBaseDocumentUploadError: On any pipeline failure (``step``
                identifies the stage: ``file_read``/``presigned_url``/
                ``s3_upload``/``kb_create``).
        """
        pipe_uuid = _require_non_blank(pipe_uuid, "pipe_uuid")
        name = _require_non_blank(name, "name")
        description = _require_bounded(
            description, "description", MAX_DOCUMENT_DESCRIPTION_LENGTH
        )

        file = await self._read_pdf(file_path)

        download_url = await self._upload_pdf(pipe_uuid, file)

        input_obj = {
            "pipeUuid": pipe_uuid,
            "name": name,
            "description": description,
            "documentUrl": download_url,
        }
        try:
            response = await self._executor.execute_query(
                CREATE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION, {"input": input_obj}
            )
            return _unwrap_document(response, "createAiKnowledgeBaseDocument")
        except Exception as exc:
            raise KnowledgeBaseDocumentUploadError(
                f"Document create failed: {exc}", step="kb_create"
            ) from exc

    async def update_ai_knowledge_base_document(
        self,
        document_id: str,
        pipe_uuid: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> KnowledgeBaseDocumentPayload:
        """Update a pipe-scoped knowledge base document (metadata only).

        Only ``name``/``description`` can change; file replacement is not
        supported. Only the fields you pass are sent; unset fields keep their
        stored value. At least one of ``name``/``description`` must be provided.

        Args:
            document_id: Document ID to update.
            pipe_uuid: Pipe UUID (not the numeric id).
            name: New name (non-blank when given).
            description: New description (1-900 chars when given).

        Returns:
            The updated document dict.
        """
        if name is None and description is None:
            raise ValueError("Provide at least one of name or description to update.")
        input_obj: dict[str, Any] = {
            "pipeUuid": _require_non_blank(pipe_uuid, "pipe_uuid"),
            "documentId": _require_non_blank(document_id, "document_id"),
        }
        if name is not None:
            input_obj["name"] = _require_non_blank(name, "name")
        if description is not None:
            input_obj["description"] = _require_bounded(
                description, "description", MAX_DOCUMENT_DESCRIPTION_LENGTH
            )
        response = await self._executor.execute_query(
            UPDATE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION, {"input": input_obj}
        )
        return _unwrap_document(response, "updateAiKnowledgeBaseDocument")

    async def delete_ai_knowledge_base_document(
        self, document_id: str, pipe_uuid: str
    ) -> KnowledgeBaseDeleteResult:
        """Delete a pipe-scoped knowledge base document (permanent).

        Args:
            document_id: Document ID to delete.
            pipe_uuid: Pipe UUID (not the numeric id).

        Returns:
            ``success`` and any backend ``errors``.
        """
        input_obj = {
            "pipeUuid": _require_non_blank(pipe_uuid, "pipe_uuid"),
            "documentId": _require_non_blank(document_id, "document_id"),
        }
        response = await self._executor.execute_query(
            DELETE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION, {"input": input_obj}
        )
        payload = response.get("deleteAiKnowledgeBaseDocument")
        payload = payload if isinstance(payload, dict) else {}
        errors = payload.get("errors")
        return {
            "success": bool(payload.get("success")),
            "errors": [str(e) for e in errors] if isinstance(errors, list) else [],
        }

    async def _read_pdf(self, file_path: str | Path) -> LocalFile:
        """Read and validate the local PDF (``file_read`` step)."""
        if Path(file_path).suffix.lower() != DOCUMENT_PDF_SUFFIX:
            raise KnowledgeBaseDocumentUploadError(
                f"File must be a .pdf: {file_path}", step="file_read"
            )
        file = LocalFile(Path(file_path), max_size_bytes=MAX_DOCUMENT_SIZE_BYTES)
        try:
            await asyncio.to_thread(file.read)
        except LocalFileError as exc:
            raise KnowledgeBaseDocumentUploadError(str(exc), step="file_read") from exc
        return file

    async def _upload_pdf(self, pipe_uuid: str, file: LocalFile) -> str:
        """Resolve the org, presign, and PUT the bytes; return the download URL.

        Covers the ``presigned_url`` and ``s3_upload`` steps.
        """
        try:
            organization_id = await self._resolve_organization_id(pipe_uuid)
            presigned = await self._create_presigned_url(
                organization_id, file.name, file.size
            )
        except KnowledgeBaseDocumentUploadError:
            raise
        except Exception as exc:
            raise KnowledgeBaseDocumentUploadError(
                f"Presigned URL request failed: {exc}", step="presigned_url"
            ) from exc

        upload_url = presigned.get("url")
        download_url = presigned.get("download_url")
        if not isinstance(upload_url, str) or not upload_url.strip():
            raise KnowledgeBaseDocumentUploadError(
                "Pipefy did not return a presigned upload URL.",
                step="presigned_url",
            )
        if not isinstance(download_url, str) or not download_url.strip():
            raise KnowledgeBaseDocumentUploadError(
                "Pipefy did not return a document download URL.",
                step="presigned_url",
            )

        try:
            put_result = await self._s3_uploader.put(
                url=upload_url.strip(),
                bytes_=file.bytes,
                content_type=DOCUMENT_CONTENT_TYPE,
            )
        except Exception as exc:
            # Transport errors and the uploader's host-allowlist rejection are
            # s3_upload-stage failures; tag them so the step contract holds.
            raise KnowledgeBaseDocumentUploadError(
                f"S3 upload failed: {exc}", step="s3_upload"
            ) from exc
        status = put_result.get("status_code", 0)
        if not isinstance(status, int) or status >= 400:
            body_snippet = put_result.get("body_snippet")
            raise KnowledgeBaseDocumentUploadError(
                f"S3 upload failed with HTTP {status}.",
                step="s3_upload",
                body_snippet=body_snippet if isinstance(body_snippet, str) else None,
                status_code=status if isinstance(status, int) else None,
            )
        return download_url.strip()

    async def _resolve_organization_id(self, pipe_uuid: str) -> str:
        """Resolve the organization id for a pipe (presign needs it)."""
        response = await self._executor.execute_query(
            GET_PIPE_ORGANIZATION_QUERY, {"id": pipe_uuid}
        )
        pipe = response.get("pipe")
        organization = pipe.get("organization") if isinstance(pipe, dict) else None
        org_id = organization.get("id") if isinstance(organization, dict) else None
        if not isinstance(org_id, str) or not org_id.strip():
            raise KnowledgeBaseDocumentUploadError(
                f"Could not resolve the organization for pipe {pipe_uuid}.",
                step="presigned_url",
            )
        return org_id.strip()

    async def _create_presigned_url(
        self, organization_id: str, file_name: str, content_length: int
    ) -> dict[str, Any]:
        """Request a presigned upload URL from Pipefy (shared mutation)."""
        payload = await self._executor.execute_query(
            CREATE_PRESIGNED_URL_MUTATION,
            {
                "organizationId": organization_id,
                "fileName": file_name,
                "contentType": DOCUMENT_CONTENT_TYPE,
                "contentLength": content_length,
            },
        )
        node = payload.get("createPresignedUrl")
        if not isinstance(node, dict):
            return {"url": None, "download_url": None}
        return {"url": node.get("url"), "download_url": node.get("downloadUrl")}

    async def validate_knowledge_base_access(
        self, pipe_uuid: str
    ) -> KnowledgeBaseAccessProbeResult:
        """Probe knowledge-base *read* access for a pipe.

        Runs the list query through the partial-success executor and classifies
        any GraphQL errors instead of raising. A green result proves read access
        only (``read_ai_agents``), never the ``manage_ai_agents`` entitlement the
        plain-text writes require — spelled out in ``note``.
        """
        variables = {"pipeUuid": _require_non_blank(pipe_uuid, "pipe_uuid")}
        result = await self._executor.execute(GET_AI_KNOWLEDGE_BASES_QUERY, variables)
        items = result.data.get("aiKnowledgeBases")
        if items is None:
            problem = classify_graphql_error_dicts(result.errors)
            if problem is None:
                problem_dict: dict[str, Any] = {
                    "kind": GraphQLProblemKind.RUNTIME.value,
                    "message": "Query returned no data and no errors.",
                }
            else:
                problem_dict = _problem_dict(problem)
            return {"ok": False, "problem": problem_dict}

        probe: KnowledgeBaseAccessProbeResult = {
            "ok": True,
            "knowledge_base_count": len(items),
            "note": _PROBE_READ_ONLY_NOTE,
        }
        # A response can carry readable data alongside per-node errors; a green
        # probe still surfaces them so partial denial is never read as full access.
        partial = classify_graphql_error_dicts(result.errors)
        if partial is not None:
            probe["note"] = (
                f"{probe['note']} The response also carried GraphQL errors; "
                "see problem."
            )
            probe["problem"] = _problem_dict(partial)
        return probe


def _unwrap_plain_text(
    response: dict[str, Any], mutation_key: str
) -> KnowledgeBasePlainTextPayload:
    """Unwrap a write mutation's plain text; a missing payload is a failure.

    A write that returns no GraphQL errors but a null ``knowledgeBasePlainText``
    must not read as success — the caller cannot know whether it persisted.
    """
    payload = response.get(mutation_key)
    if isinstance(payload, dict):
        plain_text = payload.get("knowledgeBasePlainText")
        if isinstance(plain_text, dict) and plain_text:
            return plain_text
    raise ValueError(
        f"{mutation_key} returned no plain text payload; "
        "the write may not have persisted."
    )


def _unwrap_document(
    response: dict[str, Any], mutation_key: str
) -> KnowledgeBaseDocumentPayload:
    """Unwrap a write mutation's document; a missing payload is a failure.

    A write that returns no GraphQL errors but a null ``knowledgeBaseDocument``
    must not read as success — the caller cannot know whether it persisted.
    """
    payload = response.get(mutation_key)
    if isinstance(payload, dict):
        document = payload.get("knowledgeBaseDocument")
        if isinstance(document, dict) and document:
            return document
    raise ValueError(
        f"{mutation_key} returned no document payload; "
        "the write may not have persisted."
    )
