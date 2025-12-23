"""Unit tests for PipeService.

Tests validate the pipe-related operations without requiring real API credentials.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from gql import Client

from pipefy_mcp.services.pipefy.pipe_service import PipeService


def _create_mock_gql_client(mock_session: AsyncMock) -> MagicMock:
    """Create a mock gql.Client with async context manager support."""
    mock_client = MagicMock(spec=Client)
    mock_client.__aenter__ = AsyncMock(return_value=mock_session)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_passes_pipe_id_variable():
    """Test get_pipe sends pipe_id in GraphQL variables."""
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"pipe": {"id": str(pipe_id)}})
    mock_client = _create_mock_gql_client(mock_session)

    service = PipeService(client=mock_client)
    result = await service.get_pipe(pipe_id)

    mock_session.execute.assert_called_once()
    variables = mock_session.execute.call_args[1]["variable_values"]
    assert variables == {"pipe_id": pipe_id}, "Expected pipe_id in variables"
    assert result == {"pipe": {"id": str(pipe_id)}}, "Expected pipe response"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_start_form_fields_empty_returns_message():
    """Test get_start_form_fields returns user-friendly message when no fields configured."""
    pipe_id = 303181849

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"pipe": {"start_form_fields": []}})
    mock_client = _create_mock_gql_client(mock_session)

    service = PipeService(client=mock_client)
    result = await service.get_start_form_fields(pipe_id)

    assert result == {
        "message": "This pipe has no start form fields configured.",
        "start_form_fields": [],
    }, "Expected empty fields message"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_start_form_fields_required_only_filters_and_returns_message_when_none():
    """Test get_start_form_fields with required_only=True returns message when all optional."""
    pipe_id = 303181849
    mock_fields = [
        {"id": "priority", "required": False},
        {"id": "notes", "required": False},
    ]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"pipe": {"start_form_fields": mock_fields}})
    mock_client = _create_mock_gql_client(mock_session)

    service = PipeService(client=mock_client)
    result = await service.get_start_form_fields(pipe_id, required_only=True)

    assert result == {
        "message": "This pipe has no required fields in the start form.",
        "start_form_fields": [],
    }, "Expected no required fields message"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_start_form_fields_required_only_returns_only_required():
    """Test get_start_form_fields with required_only=True filters correctly."""
    pipe_id = 303181849
    mock_fields = [
        {"id": "title", "required": True},
        {"id": "priority", "required": False},
        {"id": "due_date", "required": True},
    ]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"pipe": {"start_form_fields": mock_fields}})
    mock_client = _create_mock_gql_client(mock_session)

    service = PipeService(client=mock_client)
    result = await service.get_start_form_fields(pipe_id, required_only=True)

    expected_fields = [{"id": "title", "required": True}, {"id": "due_date", "required": True}]
    assert result == {"start_form_fields": expected_fields}, "Expected only required fields"
