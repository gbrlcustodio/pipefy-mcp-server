"""Shared test doubles for the SDK's GraphQL executor seam.

Lives in ``_shared`` so the executor stand-in is defined once and reused across
the service test modules rather than re-rolled per file.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pipefy_sdk.graphql_executor import GraphQLExecutor, PartialQueryResult


def mock_executor(
    return_value: dict | None = None,
    *,
    side_effect=None,
    partial_result: PartialQueryResult | None = None,
    partial_side_effect=None,
) -> MagicMock:
    """A MagicMock standing in for a :class:`GraphQLExecutor`.

    Pass ``return_value`` to set what ``execute_query`` resolves to, or
    ``side_effect`` for the error-path tests. Assert on the returned mock's
    ``execute_query`` to verify the query and variables a service sent.

    The partial-tolerant seam is stubbed too: ``partial_result`` sets what
    ``execute_query_allow_partial`` resolves to, and ``partial_side_effect``
    drives its error paths. Without them the spec'd mock would auto-create the
    method as an AsyncMock resolving to a bare MagicMock, so a service reading
    ``result.data``/``result.errors`` gets silent garbage instead of a failure.
    """
    mock = MagicMock(spec=GraphQLExecutor)
    mock.execute_query = AsyncMock(return_value=return_value, side_effect=side_effect)
    mock.execute_query_allow_partial = AsyncMock(
        return_value=partial_result, side_effect=partial_side_effect
    )
    return mock
