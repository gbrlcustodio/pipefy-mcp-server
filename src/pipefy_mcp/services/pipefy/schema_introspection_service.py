"""GraphQL schema introspection and ad-hoc execute against Pipefy's public endpoint."""

from __future__ import annotations

from typing import Any

from gql import gql
from gql.transport.exceptions import TransportQueryError
from graphql import GraphQLError, GraphQLSyntaxError
from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.introspection_queries import (
    INTROSPECT_MUTATION_QUERY,
    INTROSPECT_TYPE_QUERY,
    SCHEMA_TYPES_QUERY,
)
from pipefy_mcp.settings import PipefySettings


class SchemaIntrospectionService(BasePipefyClient):
    """GraphQL schema introspection against the standard Pipefy endpoint."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def introspect_type(self, type_name: str) -> dict[str, Any]:
        """Return introspection data for a schema type (object, input, enum, etc.).

        Args:
            type_name: GraphQL type name as defined in the schema.
        """
        data = await self.execute_query(
            INTROSPECT_TYPE_QUERY,
            {"typeName": type_name},
        )
        gql_type = data.get("__type")
        if gql_type is None:
            return {
                "error": f"GraphQL type '{type_name}' was not found.",
            }
        return gql_type

    async def introspect_mutation(self, mutation_name: str) -> dict[str, Any]:
        """Return name, description, arguments, and return type for a mutation field.

        Args:
            mutation_name: GraphQL mutation field name as defined on the root Mutation type.
        """
        data = await self.execute_query(INTROSPECT_MUTATION_QUERY, {})
        mutation_type = data.get("__type")
        if mutation_type is None:
            return {
                "error": "Could not introspect the root Mutation type.",
            }
        fields = mutation_type.get("fields") or []
        for field in fields:
            if field.get("name") == mutation_name:
                return {
                    "name": field["name"],
                    "description": field.get("description"),
                    "args": field.get("args") or [],
                    "type": field.get("type"),
                }
        return {
            "error": f"Mutation '{mutation_name}' was not found.",
        }

    async def search_schema(self, keyword: str) -> dict[str, Any]:
        """Search types whose name or description contains the keyword (case-insensitive).

        Types with names starting with ``__`` (introspection) are excluded.

        Args:
            keyword: Substring matched against each type's name and description.
        """
        data = await self.execute_query(SCHEMA_TYPES_QUERY, {})
        schema = data.get("__schema") or {}
        types = schema.get("types") or []
        needle = keyword.lower()
        matches: list[dict[str, Any]] = []
        for t in types:
            name = t.get("name") or ""
            if name.startswith("__"):
                continue
            description = t.get("description") or ""
            if needle in name.lower() or needle in description.lower():
                matches.append(
                    {
                        "name": name,
                        "kind": t.get("kind"),
                        "description": t.get("description"),
                    }
                )
        return {"types": matches}

    async def execute_graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Parse the document with ``gql()`` (syntax only), then execute on the Pipefy endpoint.

        Args:
            query: GraphQL query or mutation string.
            variables: Values for operation variables (optional).
        """
        try:
            document = gql(query)
        except GraphQLSyntaxError as exc:
            return {"error": str(exc)}
        try:
            return await self.execute_query(document, variables or {})
        except TransportQueryError as exc:
            errors = exc.errors if exc.errors else [{"message": str(exc)}]
            return {"errors": errors}
        except GraphQLError as exc:
            return {"errors": [{"message": str(exc)}]}
