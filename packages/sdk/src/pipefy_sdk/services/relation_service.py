"""GraphQL operations for Pipefy pipe, table, and card relations.

``CreatePipeRelationInput`` / ``UpdatePipeRelationInput`` require all boolean flags; defaults live
in ``_PIPE_RELATION_CONSTRAINT_DEFAULTS``. ``CreateCardRelationInput.sourceType`` is
``PipeRelation`` | ``Field`` (default constant: PipeRelation).

Merged ``**attrs`` / ``extra_input``: ``None`` values are omitted from GraphQL input (leave
unchanged on the server). Explicit API null to clear a field is not supported — same as
``PipeConfigService`` / ``TableService``.
"""

from __future__ import annotations

from typing import Any

from httpx import Auth

from pipefy_sdk.base_client import BasePipefyClient
from pipefy_sdk.queries.relation_queries import (
    CREATE_CARD_RELATION_MUTATION,
    CREATE_PIPE_RELATION_MUTATION,
    DELETE_PIPE_RELATION_MUTATION,
    GET_PIPE_RELATIONS_QUERY,
    GET_TABLE_RELATIONS_QUERY,
    INTERNAL_DELETE_CARD_RELATION_MUTATION,
    UPDATE_PIPE_RELATION_MUTATION,
)
from pipefy_sdk.services.internal_api_client import InternalApiClient
from pipefy_sdk.settings import PipefySettings

INTERNAL_API_CLIENT_NOT_CONFIGURED = "Internal API client is not configured."

_PIPE_RELATION_CONSTRAINT_DEFAULTS: dict[str, Any] = {
    "allChildrenMustBeDoneToFinishParent": False,
    "allChildrenMustBeDoneToMoveParent": False,
    "autoFillFieldEnabled": False,
    "canConnectExistingItems": True,
    "canConnectMultipleItems": True,
    "canCreateNewItems": True,
    "childMustExistToFinishParent": False,
    "childMustExistToMoveParent": False,
}

_DEFAULT_CARD_RELATION_SOURCE_TYPE = "PipeRelation"


class RelationService(BasePipefyClient):
    """Reads and mutations for pipe relations, table relations (by relation ID), and card links."""

    def __init__(
        self,
        settings: PipefySettings,
        *,
        auth: Auth,
        internal_api_client: InternalApiClient | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)
        self._internal_api_client = internal_api_client

    async def get_pipe_relations(self, pipe_id: str | int) -> dict[str, Any]:
        """Fetch parent and child pipe relations for a pipe (`parentsRelations`, `childrenRelations`).

        Args:
            pipe_id: Pipe ID.
        """
        return await self.execute_query(
            GET_PIPE_RELATIONS_QUERY,
            {"pipeId": str(pipe_id)},
        )

    async def get_table_relations(
        self, relation_ids: list[str | int]
    ) -> dict[str, Any]:
        """Batch-fetch table relations by ID (root `table_relations` query).

        Args:
            relation_ids: One or more **table relation** IDs (not the database table ID).
        """
        return await self.execute_query(
            GET_TABLE_RELATIONS_QUERY,
            {"ids": [str(r) for r in relation_ids]},
        )

    async def create_pipe_relation(
        self,
        parent_id: str | int,
        child_id: str | int,
        name: str,
        **attrs: Any,
    ) -> dict[str, Any]:
        """Create a parent-child pipe relation (`CreatePipeRelationInput`).

        Args:
            parent_id: Parent pipe ID.
            child_id: Child pipe ID.
            name: Relation label.
            **attrs: Extra `CreatePipeRelationInput` fields (camelCase keys), e.g. ``ownFieldMaps``.
        """
        input_obj: dict[str, Any] = {
            "parentId": str(parent_id),
            "childId": str(child_id),
            "name": name,
            **_PIPE_RELATION_CONSTRAINT_DEFAULTS,
        }
        for key, value in attrs.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            CREATE_PIPE_RELATION_MUTATION,
            {"input": input_obj},
        )

    async def update_pipe_relation(
        self,
        relation_id: str | int,
        name: str,
        **attrs: Any,
    ) -> dict[str, Any]:
        """Update a pipe relation (`UpdatePipeRelationInput`).

        Args:
            relation_id: Pipe relation ID.
            name: Relation name (required by the API).
            **attrs: Extra `UpdatePipeRelationInput` fields (camelCase keys), overriding defaults.
        """
        input_obj: dict[str, Any] = {
            "id": str(relation_id),
            "name": name,
            **_PIPE_RELATION_CONSTRAINT_DEFAULTS,
        }
        for key, value in attrs.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            UPDATE_PIPE_RELATION_MUTATION,
            {"input": input_obj},
        )

    async def delete_pipe_relation(self, relation_id: str | int) -> dict[str, Any]:
        """Delete a pipe relation by ID (permanent).

        Args:
            relation_id: Pipe relation ID.
        """
        return await self.execute_query(
            DELETE_PIPE_RELATION_MUTATION,
            {"input": {"id": str(relation_id)}},
        )

    async def create_card_relation(
        self,
        parent_id: str | int,
        child_id: str | int,
        source_id: str | int,
        **attrs: Any,
    ) -> dict[str, Any]:
        """Connect two cards via a pipe relation (`CreateCardRelationInput`).

        Args:
            parent_id: Parent card ID.
            child_id: Child card ID.
            source_id: Pipe relation ID (from ``get_pipe_relations`` / ``parentsRelations`` / ``childrenRelations``).
            **attrs: Optional overrides, e.g. ``sourceType`` (default ``PipeRelation``; API also allows ``Field``).
        """
        input_obj: dict[str, Any] = {
            "parentId": str(parent_id),
            "childId": str(child_id),
            "sourceId": str(source_id),
            "sourceType": _DEFAULT_CARD_RELATION_SOURCE_TYPE,
        }
        for key, value in attrs.items():
            if value is not None:
                input_obj[key] = value
        return await self.execute_query(
            CREATE_CARD_RELATION_MUTATION,
            {"input": input_obj},
        )

    async def delete_card_relation(
        self,
        child_id: str | int,
        parent_id: str | int,
        source_id: str | int,
    ) -> dict[str, Any]:
        """Delete a relation link between two cards (internal API, requires OAuth).

        The ``deleteCardRelation`` mutation is not exposed on the public GraphQL
        schema, only on the internal API (core_api / internal_v1), so it routes
        through the injected ``InternalApiClient`` rather than ``execute_query``.

        Args:
            child_id: Child card ID.
            parent_id: Parent card ID.
            source_id: Pipe relation ID linking the two cards.

        Raises:
            ValueError: When no internal API client was injected.
        """
        if self._internal_api_client is None:
            raise ValueError(INTERNAL_API_CLIENT_NOT_CONFIGURED)
        return await self._internal_api_client.execute_query(
            INTERNAL_DELETE_CARD_RELATION_MUTATION,
            {
                "childId": str(child_id),
                "parentId": str(parent_id),
                "sourceId": str(source_id),
            },
        )
