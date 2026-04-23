"""GraphQL schema introspection and ad-hoc execute against Pipefy's public endpoint."""

from __future__ import annotations

import logging
import re
from typing import Any

from gql import gql
from gql.transport.exceptions import TransportQueryError
from graphql import GraphQLError, GraphQLSyntaxError
from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
from pipefy_mcp.services.pipefy.queries.introspection_queries import (
    INTROSPECT_MUTATION_QUERY,
    INTROSPECT_QUERY_QUERY,
    INTROSPECT_TYPE_QUERY,
    SCHEMA_TYPES_QUERY,
)
from pipefy_mcp.settings import PipefySettings

logger = logging.getLogger(__name__)


class SchemaIntrospectionService(BasePipefyClient):
    """GraphQL schema introspection against the standard Pipefy endpoint."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: OAuth2ClientCredentials | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    _SCALAR_TYPE_NAMES = frozenset(
        {
            "ID",
            "String",
            "Int",
            "Float",
            "Boolean",
            "DateTime",
        }
    )

    async def introspect_type(
        self, type_name: str, *, max_depth: int = 1
    ) -> dict[str, Any]:
        """Return introspection data for a schema type (object, input, enum, etc.).

        Args:
            type_name: GraphQL type name as defined in the schema.
            max_depth: How many levels of referenced types to resolve (default 1 = no recursion).
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
        if max_depth > 1:
            await self._resolve_type_references(gql_type, 1, max_depth)
        return gql_type

    def _extract_type_name(self, type_info: dict[str, Any] | None) -> str | None:
        """Extract the concrete type name, unwrapping NON_NULL/LIST wrappers."""
        current = type_info
        while isinstance(current, dict):
            name = current.get("name")
            if name:
                return name
            current = current.get("ofType")
        return None

    async def _resolve_type_references(
        self,
        type_data: dict[str, Any],
        current_depth: int,
        max_depth: int,
    ) -> None:
        """Walk fields/inputFields/args and inline resolved types up to max_depth.

        Args:
            type_data: The introspected type dict to enrich in-place.
            current_depth: Current recursion depth.
            max_depth: Maximum depth to resolve.
        """
        if current_depth >= max_depth:
            return

        items_to_resolve: list[dict[str, Any]] = []
        for key in ("fields", "inputFields", "args"):
            entries = type_data.get(key)
            if isinstance(entries, list):
                items_to_resolve.extend(entries)

        for item in items_to_resolve:
            ref_name = self._extract_type_name(item.get("type"))
            if ref_name is None or ref_name in self._SCALAR_TYPE_NAMES:
                continue
            resolved = await self.introspect_type(ref_name, max_depth=1)
            if "error" not in resolved:
                item["resolvedType"] = resolved

    async def _introspect_root_field(
        self,
        root_type_label: str,
        field_name: str,
        query_constant: Any,
        *,
        max_depth: int = 1,
    ) -> dict[str, Any]:
        """Shared logic for introspecting a field on a root type (Query or Mutation).

        Args:
            root_type_label: Human-readable root type name (e.g. "Query", "Mutation").
            field_name: Field name to look up on the root type.
            query_constant: Pre-compiled ``gql()`` introspection query for the root type.
            max_depth: How many levels of referenced types to resolve (default 1).
        """
        data = await self.execute_query(query_constant, {})
        root_type = data.get("__type")
        if root_type is None:
            return {
                "error": f"Could not introspect the root {root_type_label} type.",
            }
        fields = root_type.get("fields") or []
        for field in fields:
            if field.get("name") == field_name:
                result = {
                    "name": field["name"],
                    "description": field.get("description"),
                    "args": field.get("args") or [],
                    "type": field.get("type"),
                }
                if max_depth > 1:
                    await self._resolve_type_references(result, 1, max_depth)
                return result
        return {
            "error": f"{root_type_label} '{field_name}' was not found.",
        }

    async def introspect_mutation(
        self, mutation_name: str, *, max_depth: int = 1
    ) -> dict[str, Any]:
        """Return name, description, arguments, and return type for a mutation field.

        Args:
            mutation_name: GraphQL mutation field name as defined on the root Mutation type.
            max_depth: How many levels of referenced types to resolve (default 1).
        """
        return await self._introspect_root_field(
            "Mutation", mutation_name, INTROSPECT_MUTATION_QUERY, max_depth=max_depth
        )

    async def introspect_query(
        self, query_name: str, *, max_depth: int = 1
    ) -> dict[str, Any]:
        """Return name, description, arguments, and return type for a query field.

        Args:
            query_name: GraphQL query field name as defined on the root Query type.
            max_depth: How many levels of referenced types to resolve (default 1).
        """
        return await self._introspect_root_field(
            "Query", query_name, INTROSPECT_QUERY_QUERY, max_depth=max_depth
        )

    async def search_schema(
        self, keyword: str, *, kind: str | None = None
    ) -> dict[str, Any]:
        """Search types whose name or description contains the keyword (case-insensitive).

        Types with names starting with ``__`` (introspection) are excluded.

        Args:
            keyword: Substring matched against each type's name and description.
            kind: Optional GraphQL type kind filter (e.g. OBJECT, INPUT_OBJECT, ENUM).
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
        if kind is not None:
            matches = [m for m in matches if m.get("kind") == kind]
        return {"types": matches}

    _FIELD_NOT_FOUND_RE = re.compile(
        r"Cannot query field ['\"`](\w+)['\"`] on type ['\"`](Query|Mutation)['\"`]"
    )
    _ROOT_TYPE_QUERIES = {
        "Query": INTROSPECT_QUERY_QUERY,
        "Mutation": INTROSPECT_MUTATION_QUERY,
    }

    async def _detect_root_type_mismatch_hint(self, error_message: str) -> str | None:
        """Check if a field-not-found error is a query/mutation mismatch.

        Args:
            error_message: The GraphQL error message string.
        """
        match = self._FIELD_NOT_FOUND_RE.search(error_message)
        if not match:
            return None
        field_name, current_type = match.group(1), match.group(2)
        other_type = "Mutation" if current_type == "Query" else "Query"
        try:
            query_constant = self._ROOT_TYPE_QUERIES[other_type]
            data = await self.execute_query(query_constant, {})
            root = data.get("__type")
            if root is None:
                return None
            for field in root.get("fields") or []:
                if field.get("name") == field_name:
                    return (
                        f"Hint: '{field_name}' exists as a {other_type.lower()}, "
                        f"not a {current_type.lower()}. "
                        f"Use a {other_type.lower()} operation instead."
                    )
        except (TransportQueryError, GraphQLError, KeyError, TypeError):
            return None
        except Exception:
            logger.exception(
                "Unexpected error while detecting root type mismatch hint for field %r",
                field_name,
            )
            raise
        return None

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
            errors = list(exc.errors) if exc.errors else [{"message": str(exc)}]
            for err in errors:
                if isinstance(err, dict):
                    msg = err.get("message", "")
                    hint = await self._detect_root_type_mismatch_hint(msg)
                    if hint:
                        err["hint"] = hint
            return {"errors": errors}
        except GraphQLError as exc:
            return {"errors": [{"message": str(exc)}]}
