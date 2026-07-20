"""Shared test doubles for the SDK's GraphQL executor seam.

Lives in ``_shared`` so the executor stand-in is defined once and reused across
the service test modules rather than re-rolled per file.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pipefy_sdk.graphql_executor import GraphQLExecutor, GraphQLResult


def mock_executor(
    return_value: dict | None = None,
    *,
    side_effect=None,
    execute_result: GraphQLResult | None = None,
    execute_side_effect=None,
) -> MagicMock:
    """A MagicMock standing in for a :class:`GraphQLExecutor`.

    ``return_value``/``side_effect`` drive ``execute_query``, the raise-on-error
    convenience most services call. ``execute_result``/``execute_side_effect``
    drive ``execute``, the primitive that hands back data and errors together.
    Both are stubbed explicitly: an auto-created method would resolve to a bare
    MagicMock and feed services silent garbage instead of a failure.
    """
    mock = MagicMock(spec=GraphQLExecutor)
    mock.execute_query = AsyncMock(return_value=return_value, side_effect=side_effect)
    mock.execute = AsyncMock(
        return_value=execute_result, side_effect=execute_side_effect
    )
    return mock
