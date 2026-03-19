"""GraphQL operations for Pipefy pipe, table, and card relations."""

from __future__ import annotations

from typing import Any

from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.relation_queries import (
    CREATE_CARD_RELATION_MUTATION,
    CREATE_PIPE_RELATION_MUTATION,
    DELETE_PIPE_RELATION_MUTATION,
    GET_PIPE_RELATIONS_QUERY,
    GET_TABLE_RELATIONS_QUERY,
    UPDATE_PIPE_RELATION_MUTATION,
)
from pipefy_mcp.settings import PipefySettings

# CreatePipeRelationInput / UpdatePipeRelationInput boolean defaults (API requires all flags).
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

# Pipefy `CreateCardRelationInput.sourceType`: PipeRelation | Field
_DEFAULT_CARD_RELATION_SOURCE_TYPE = "PipeRelation"


class RelationService(BasePipefyClient):
    """Pipe/table relation reads and mutations."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def get_pipe_relations(self, pipe_id: str | int) -> dict[str, Any]:
        """Fetch parent and child pipe relations for a pipe (`parentsRelations`, `childrenRelations`).

        Args:
            pipe_id: Pipe ID.
        """
        return await self.execute_query(
            GET_PIPE_RELATIONS_QUERY,
            {"pipeId": pipe_id},
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
            {"ids": list(relation_ids)},
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
