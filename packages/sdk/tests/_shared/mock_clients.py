"""Shared test doubles for the SDK's endpoint clients.

Lives in ``_shared`` so the InternalApiClient stand-in is defined once and
reused across the service test modules (``test_relation_service``,
``test_portal_service``) rather than re-rolled per file.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pipefy_sdk.services.internal_api_client import InternalApiClient


def mock_internal_api_client(return_value: dict | None = None) -> MagicMock:
    """A MagicMock standing in for InternalApiClient with execute_query async.

    Pass ``return_value`` to set what ``execute_query`` resolves to; the default
    suits callers that only need a constructor stand-in and never assert on it.
    """
    mock = MagicMock(spec=InternalApiClient)
    mock.execute_query = AsyncMock(return_value=return_value)
    return mock
