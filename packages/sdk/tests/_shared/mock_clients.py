"""Shared test doubles for the SDK's GraphQL executor seam.

Lives in ``_shared`` so the executor stand-in is defined once and reused across
the service test modules rather than re-rolled per file.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pipefy_sdk.graphql_executor import PartialGraphQLExecutor, PartialQueryResult


def mock_executor(
    return_value: dict | None = None,
    *,
    side_effect=None,
    partial_result: PartialQueryResult | None = None,
    partial_side_effect=None,
) -> MagicMock:
    """A MagicMock standing in for a :class:`PartialGraphQLExecutor`.

    Spec'd on the wide protocol so one fake serves every service.
    ``return_value``/``side_effect`` drive ``execute_query``;
    ``partial_result``/``partial_side_effect`` drive
    ``execute_query_allow_partial``. Both are stubbed explicitly: an
    auto-created method would resolve to a bare MagicMock and feed services
    silent garbage instead of a failure.
    """
    mock = MagicMock(spec=PartialGraphQLExecutor)
    mock.execute_query = AsyncMock(return_value=return_value, side_effect=side_effect)
    mock.execute_query_allow_partial = AsyncMock(
        return_value=partial_result, side_effect=partial_side_effect
    )
    return mock
