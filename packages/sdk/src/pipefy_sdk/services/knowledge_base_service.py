"""Service for pipe-scoped AI knowledge bases: list, plain text CRUD, and probe.

Client-side limits fail fast before the network call so callers get an
actionable ``ValueError`` instead of a backend 422. The limits mirror the
downstream ``DataSource``/``KnowledgeBasePlainText`` model validations:
``content`` and ``name`` are required and ``content`` is capped at 3500 chars;
``description`` is required (the GraphQL schema marks it optional, but the
backend rejects a blank one) and capped at 900 chars. Updates omit any field the
caller leaves unset, but validate every field they do pass.
"""

from __future__ import annotations

from typing import Any

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.graphql_problem import (
    GraphQLProblem,
    GraphQLProblemKind,
    classify_graphql_error_dicts,
)
from pipefy_sdk.queries.knowledge_base_queries import (
    CREATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION,
    DELETE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION,
    GET_AI_KNOWLEDGE_BASE_PLAIN_TEXT_QUERY,
    GET_AI_KNOWLEDGE_BASES_QUERY,
    UPDATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION,
)
from pipefy_sdk.services.types import (
    KnowledgeBaseAccessProbeResult,
    KnowledgeBaseDeleteResult,
    KnowledgeBasePayload,
    KnowledgeBasePlainTextPayload,
)

MAX_PLAIN_TEXT_CONTENT_LENGTH = 3500
MAX_PLAIN_TEXT_DESCRIPTION_LENGTH = 900

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
    """Pipe-scoped AI knowledge base reads, plain-text writes, and the probe."""

    def __init__(self, *, executor: GraphQLExecutor) -> None:
        self._executor = executor

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
    payload = response.get(mutation_key)
    if isinstance(payload, dict):
        plain_text = payload.get("knowledgeBasePlainText")
        if isinstance(plain_text, dict):
            return plain_text
    return {}
