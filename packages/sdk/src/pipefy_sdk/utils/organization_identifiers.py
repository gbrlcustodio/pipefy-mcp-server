"""Helpers for organization UUID vs numeric id resolution."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from graphql import DocumentNode

from pipefy_sdk.queries.observability_queries import RESOLVE_ORGANIZATION_UUID_QUERY

ExecuteQuery = Callable[[DocumentNode, dict[str, Any]], Awaitable[dict[str, Any]]]


def looks_like_uuid(value: str) -> bool:
    """True when ``value`` parses as a UUID."""
    try:
        uuid.UUID(value.strip())
    except ValueError:
        return False
    return True


async def resolve_organization_uuid(
    execute_query: ExecuteQuery,
    organization_identifier: str | int,
) -> str:
    """Resolve UUID-or-numeric organization identifier to a UUID via public GraphQL.

    Args:
        execute_query: Async GraphQL executor (public schema ``/graphql``).
        organization_identifier: Organization UUID or numeric organization id.

    Returns:
        Organization UUID string for GraphQL variables.

    Raises:
        ValueError: When the identifier is empty, invalid, or resolution yields no uuid.
    """
    if isinstance(organization_identifier, int):
        organization_identifier = str(organization_identifier)
    trimmed = organization_identifier.strip()
    if not trimmed:
        raise ValueError("organization identifier must be non-empty")
    if looks_like_uuid(trimmed):
        return trimmed
    if trimmed.isdigit():
        result = await execute_query(
            RESOLVE_ORGANIZATION_UUID_QUERY,
            {"id": str(trimmed)},
        )
        org = result.get("organization")
        uuid_value = org.get("uuid") if isinstance(org, dict) else None
        if not uuid_value:
            raise ValueError(f"Organization not found or has no uuid for id: {trimmed}")
        return str(uuid_value)
    raise ValueError(
        f"organization identifier must be a UUID or numeric id, got: {trimmed!r}"
    )
