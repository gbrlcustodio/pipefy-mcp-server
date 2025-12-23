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


@pytest.fixture
def mock_organizations() -> list[dict]:
    """Shared mock data for search_pipes tests."""
    return [
        {
            "id": "1",
            "name": "Custaudio Org",
            "pipes": [
                {"id": "47", "name": "Custaudio pipe"},
                {"id": "100", "name": "Custaudio"},
                {"id": "101", "name": "Drico pipe"},
            ],
        },
        {
            "id": "2",
            "name": "Dao Org",
            "pipes": [{"id": "201", "name": "Sales Pipe"}],
        },
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_pipes_without_name_returns_all(mock_organizations: list[dict]):
    """Test search_pipes returns all organizations and pipes when no name filter provided."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"organizations": mock_organizations})
    mock_client = _create_mock_gql_client(mock_session)

    service = PipeService(client=mock_client)
    result = await service.search_pipes()

    assert result == {"organizations": mock_organizations}, "Expected all organizations returned"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("search_term", "expected_org_ids", "expected_pipe_names", "expected_pipe_scores"),
    [
        pytest.param(
            "Custaudio",
            ["1"],
            [["Custaudio", "Custaudio pipe"]],
            [[100.0, 90.0]],
            id="exact_match_ranked_first",
        ),
        pytest.param(
            "custaudio",
            ["1"],
            [["Custaudio", "Custaudio pipe"]],
            [[88.9, 80.0]],
            id="case_insensitive_match",
        ),
        pytest.param(
            "Sales",
            ["2"],
            [["Sales Pipe"]],
            [[90.0]],
            id="partial_match",
        ),
        pytest.param(
            "drico",
            ["1"],
            [["Drico pipe"]],
            [[72.0]],
            id="single_match_in_org",
        ),
        pytest.param(
            "pipe",
            ["1", "2"],
            [["Custaudio pipe", "Drico pipe"], ["Sales Pipe"]],
            [[90.0, 90.0], [77.1]],
            id="matches_across_multiple_orgs",
        ),
    ],
)
async def test_search_pipes_fuzzy_matching(
    mock_organizations: list[dict],
    search_term: str,
    expected_org_ids: list[str],
    expected_pipe_names: list[list[str]],
    expected_pipe_scores: list[list[float]],
):
    """Test search_pipes fuzzy matching filters and sorts correctly."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"organizations": mock_organizations})
    mock_client = _create_mock_gql_client(mock_session)

    service = PipeService(client=mock_client)
    result = await service.search_pipes(pipe_name=search_term)

    assert len(result["organizations"]) == len(expected_org_ids)
    for i, org in enumerate(result["organizations"]):
        assert org["id"] == expected_org_ids[i]
        pipe_names = [p["name"] for p in org["pipes"]]
        assert pipe_names == expected_pipe_names[i]
        scores = [p["match_score"] for p in org["pipes"]]
        assert scores == expected_pipe_scores[i], f"Expected scores {expected_pipe_scores[i]}, got {scores}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_pipes_no_matches_returns_empty(mock_organizations: list[dict]):
    """Test search_pipes returns empty list when no pipes match the search term."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value={"organizations": mock_organizations})
    mock_client = _create_mock_gql_client(mock_session)

    service = PipeService(client=mock_client)
    result = await service.search_pipes(pipe_name="Dão")

    assert result == {"organizations": []}, "Expected empty organizations when no matches"
