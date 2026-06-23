"""Shared test doubles for the SDK's GraphQL executor seam.

Lives in ``_shared`` so the executor stand-in is defined once and reused across
the service test modules rather than re-rolled per file.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.services.internal_api_client import InternalApiClient


def mock_executor(return_value: dict | None = None, *, side_effect=None) -> MagicMock:
    """A MagicMock standing in for a :class:`GraphQLExecutor`.

    Pass ``return_value`` to set what ``execute_query`` resolves to, or
    ``side_effect`` for the error-path tests. Assert on the returned mock's
    ``execute_query`` to verify the query and variables a service sent.
    """
    mock = MagicMock(spec=GraphQLExecutor)
    mock.execute_query = AsyncMock(return_value=return_value, side_effect=side_effect)
    return mock


def mock_internal_api_client(return_value: dict | None = None) -> MagicMock:
    """A MagicMock standing in for InternalApiClient with execute_query async.

    Pass ``return_value`` to set what ``execute_query`` resolves to; the default
    suits callers that only need a constructor stand-in and never assert on it.
    """
    mock = MagicMock(spec=InternalApiClient)
    mock.execute_query = AsyncMock(return_value=return_value)
    return mock
