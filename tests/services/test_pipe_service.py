"""Unit tests for PipeService.

Tests validate the pipe-related operations without requiring real API credentials.
"""

from unittest.mock import AsyncMock

import pytest
from graphql import print_ast

from pipefy_mcp.services.pipefy.pipe_service import PipeService
from pipefy_mcp.services.pipefy.queries.pipe_queries import (
    GET_PHASE_ALLOWED_MOVES_QUERY,
    GET_PHASE_FIELDS_QUERY,
)
from pipefy_mcp.settings import PipefySettings


@pytest.fixture
def mock_settings() -> PipefySettings:
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value):
    service = PipeService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_passes_pipe_id_variable(mock_settings):
    """Test get_pipe sends pipe_id in GraphQL variables."""
    pipe_id = 303181849

    service = _make_service(mock_settings, {"pipe": {"id": str(pipe_id)}})
    result = await service.get_pipe(pipe_id)

    service.execute_query.assert_called_once()
    variables = service.execute_query.call_args[0][1]
    assert variables == {"pipe_id": str(pipe_id)}, "Expected pipe_id in variables"
    assert result == {"pipe": {"id": str(pipe_id)}}, "Expected pipe response"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_members_returns_members(mock_settings):
    """Test get_pipe_members returns the list of members for a pipe."""
    pipe_id = 123
    mock_members = [
        {
            "user": {"id": "1", "name": "John Doe", "email": "john.doe@example.com"},
            "role_name": "Admin",
        },
        {
            "user": {
                "id": "2",
                "name": "Jane Smith",
                "email": "jane.smith@example.com",
            },
            "role_name": "Member",
        },
    ]

    service = _make_service(mock_settings, {"pipe": {"members": mock_members}})
    result = await service.get_pipe_members(pipe_id)

    service.execute_query.assert_called_once()
    variables = service.execute_query.call_args[0][1]
    assert variables == {"pipeId": str(pipe_id)}, "Expected pipeId in variables"
    assert result == {"pipe": {"members": mock_members}}, (
        "Expected pipe members response"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_start_form_fields_empty_returns_message(mock_settings):
    """Test get_start_form_fields returns user-friendly message when no fields configured."""
    pipe_id = 303181849

    service = _make_service(mock_settings, {"pipe": {"start_form_fields": []}})
    result = await service.get_start_form_fields(pipe_id)

    assert result == {
        "message": "This pipe has no start form fields configured.",
        "start_form_fields": [],
    }, "Expected empty fields message"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_start_form_fields_required_only_filters_and_returns_message_when_none(
    mock_settings,
):
    """Test get_start_form_fields with required_only=True returns message when all optional."""
    pipe_id = 303181849
    mock_fields = [
        {"id": "priority", "required": False},
        {"id": "notes", "required": False},
    ]

    service = _make_service(mock_settings, {"pipe": {"start_form_fields": mock_fields}})
    result = await service.get_start_form_fields(pipe_id, required_only=True)

    assert result == {
        "message": "This pipe has no required fields in the start form.",
        "start_form_fields": [],
    }, "Expected no required fields message"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_start_form_fields_required_only_returns_only_required(mock_settings):
    """Test get_start_form_fields with required_only=True filters correctly."""
    pipe_id = 303181849
    mock_fields = [
        {"id": "title", "required": True},
        {"id": "priority", "required": False},
        {"id": "due_date", "required": True},
    ]

    service = _make_service(mock_settings, {"pipe": {"start_form_fields": mock_fields}})
    result = await service.get_start_form_fields(pipe_id, required_only=True)

    expected_fields = [
        {"id": "title", "required": True},
        {"id": "due_date", "required": True},
    ]
    assert result == {"start_form_fields": expected_fields}, (
        "Expected only required fields"
    )


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
            "name": "Organização Brasil",
            "pipes": [
                {"id": "201", "name": "Vendas São Paulo"},
                {"id": "202", "name": "Gestão de Clientes"},
                {"id": "203", "name": "Produção"},
                {"id": "204", "name": "Contratação"},
            ],
        },
        {
            "id": "3",
            "name": "Tech Org",
            "pipes": [
                {"id": "301", "name": "Bug Tracker [v2.0]"},
                {"id": "302", "name": "Sales & Marketing"},
                {"id": "303", "name": "R&D / Innovation"},
            ],
        },
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_pipes_without_name_returns_all(
    mock_settings, mock_organizations: list[dict]
):
    """Test search_pipes returns all organizations and pipes when no name filter provided."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_pipes()

    assert result == {"organizations": mock_organizations}, (
        "Expected all organizations returned"
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("search_term", "expected_org_ids", "expected_pipe_names", "expected_pipe_scores"),
    [
        pytest.param(
            "Custaudio",
            ["1"],
            [["Custaudio pipe", "Custaudio"]],
            [[100.0, 100.0]],
            id="exact_match_ranked_first",
        ),
        pytest.param(
            "custaudio",
            ["1"],
            [["Custaudio pipe", "Custaudio"]],
            [[100.0, 100.0]],
            id="case_insensitive_match",
        ),
        pytest.param(
            "drico",
            ["1"],
            [["Drico pipe"]],
            [[100.0]],
            id="single_match_in_org",
        ),
        pytest.param(
            "pipe",
            ["1"],
            [["Custaudio pipe", "Drico pipe"]],
            [[100.0, 100.0]],
            id="matches_across_multiple_pipes",
        ),
        pytest.param(
            "Vendas",
            ["2"],
            [["Vendas São Paulo"]],
            [[100.0]],
            id="accented_substring_match",
        ),
        pytest.param(
            "São Paulo",
            ["2"],
            [["Vendas São Paulo"]],
            [[100.0]],
            id="accented_exact_substring",
        ),
        pytest.param(
            "Sao Paulo",
            ["2"],
            [["Vendas São Paulo"]],
            [[85.5]],
            id="unaccented_matches_accented",
        ),
        pytest.param(
            "Gestao",
            ["2"],
            [["Gestão de Clientes"]],
            [[75.0]],
            id="unaccented_matches_tilde",
        ),
        pytest.param(
            "Contratação",
            ["2"],
            [["Contratação"]],
            [[100.0]],
            id="exact_accented_match",
        ),
        pytest.param(
            "Producao",
            ["2"],
            [["Produção"]],
            [[75.0]],
            id="unaccented_matches_cedilla",
        ),
        pytest.param(
            "Bug Tracker",
            ["3"],
            [["Bug Tracker [v2.0]"]],
            [[100.0]],
            id="special_chars_brackets",
        ),
        pytest.param(
            "Sales & Marketing",
            ["3"],
            [["Sales & Marketing"]],
            [[100.0]],
            id="special_chars_ampersand",
        ),
        pytest.param(
            "R&D",
            ["3"],
            [["R&D / Innovation"]],
            [[100.0]],
            id="special_chars_ampersand_slash",
        ),
    ],
)
async def test_search_pipes_fuzzy_matching(
    mock_settings,
    mock_organizations: list[dict],
    search_term: str,
    expected_org_ids: list[str],
    expected_pipe_names: list[list[str]],
    expected_pipe_scores: list[list[float]],
):
    """Test search_pipes fuzzy matching filters and sorts correctly."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_pipes(pipe_name=search_term)

    assert len(result["organizations"]) == len(expected_org_ids)
    for i, org in enumerate(result["organizations"]):
        assert org["id"] == expected_org_ids[i]
        pipe_names = [p["name"] for p in org["pipes"]]
        assert pipe_names == expected_pipe_names[i]
        scores = [p["match_score"] for p in org["pipes"]]
        assert scores == expected_pipe_scores[i], (
            f"Expected scores {expected_pipe_scores[i]}, got {scores}"
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_pipes_no_matches_returns_empty(
    mock_settings, mock_organizations: list[dict]
):
    """Test search_pipes returns empty list when no pipes match the search term."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_pipes(pipe_name="XyzNonExistent123")

    assert result == {"organizations": []}, (
        "Expected empty organizations when no matches"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_pipes_empty_organizations(mock_settings):
    """Test search_pipes handles organizations with no pipes."""
    mock_orgs = [
        {
            "id": "1",
            "name": "Empty Org",
            "pipes": [],
        },
        {
            "id": "2",
            "name": "Org with pipes",
            "pipes": [{"id": "201", "name": "Test Pipe"}],
        },
    ]

    service = PipeService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value={"organizations": mock_orgs})

    result = await service.search_pipes()
    assert len(result["organizations"]) == 2

    result = await service.search_pipes(pipe_name="Test")
    assert len(result["organizations"]) == 1
    assert result["organizations"][0]["id"] == "2"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_pipes_all_organizations_empty(mock_settings):
    """Test search_pipes handles API response with no organizations."""
    service = PipeService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value={"organizations": []})

    result = await service.search_pipes()
    assert result == {"organizations": []}

    result = await service.search_pipes(pipe_name="anything")
    assert result == {"organizations": []}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_pipes_short_keyword_matches_substring(
    mock_settings,
    mock_organizations,
):
    """Substring match finds pipes even when fuzzy score is below threshold."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_pipes(pipe_name="pipe")
    pipe_names = [p["name"] for org in result["organizations"] for p in org["pipes"]]
    assert "Custaudio pipe" in pipe_names
    assert "Drico pipe" in pipe_names


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_pipes_case_insensitive_substring(
    mock_settings,
    mock_organizations,
):
    """Case-insensitive substring matches correctly."""
    service = _make_service(mock_settings, {"organizations": mock_organizations})
    result = await service.search_pipes(pipe_name="bug")
    pipe_names = [p["name"] for org in result["organizations"] for p in org["pipes"]]
    assert "Bug Tracker [v2.0]" in pipe_names


@pytest.mark.unit
def test_get_phase_fields_query_selects_internal_id_and_uuid():
    printed = print_ast(GET_PHASE_FIELDS_QUERY)
    assert "internal_id" in printed
    assert "uuid" in printed


@pytest.mark.unit
def test_get_phase_allowed_moves_query_requests_transition_field():
    printed = print_ast(GET_PHASE_ALLOWED_MOVES_QUERY)
    assert "cards_can_be_moved_to_phases" in printed


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_phase_allowed_move_targets_sends_phase_id(mock_settings):
    phase_id = 342182335
    api_response = {
        "phase": {
            "id": str(phase_id),
            "name": "Doing",
            "cards_can_be_moved_to_phases": [{"id": "200", "name": "Done"}],
        }
    }
    service = _make_service(mock_settings, api_response)
    result = await service.get_phase_allowed_move_targets(phase_id)

    service.execute_query.assert_called_once()
    assert service.execute_query.call_args[0][0] is GET_PHASE_ALLOWED_MOVES_QUERY
    assert service.execute_query.call_args[0][1] == {"phase_id": str(phase_id)}
    assert result == api_response


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetPhaseFields:
    """Tests for get_phase_fields method."""

    PHASE_ID = 12345

    @pytest.fixture
    def mock_phase_service(self, mock_settings):
        """Factory fixture to create a PipeService with mocked phase response."""

        def _create(phase_response: dict):
            service = PipeService(settings=mock_settings)
            service.execute_query = AsyncMock(return_value={"phase": phase_response})
            return service, service.execute_query

        return _create

    async def test_returns_all_fields(self, mock_phase_service):
        """Test get_phase_fields returns all fields for a phase."""
        mock_fields = [
            {
                "id": "status",
                "internal_id": "308111001",
                "uuid": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                "label": "Status",
                "type": "select",
                "required": True,
            },
            {
                "id": "notes",
                "internal_id": "308111002",
                "uuid": "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22",
                "label": "Notes",
                "type": "long_text",
                "required": False,
            },
        ]
        service, mock_eq = mock_phase_service(
            {"id": str(self.PHASE_ID), "name": "In Progress", "fields": mock_fields}
        )

        result = await service.get_phase_fields(self.PHASE_ID)

        mock_eq.assert_called_once()
        assert mock_eq.call_args[0][0] is GET_PHASE_FIELDS_QUERY
        variables = mock_eq.call_args[0][1]
        assert variables == {"phase_id": str(self.PHASE_ID)}, (
            "Expected phase_id in variables"
        )
        assert result == {
            "phase_id": str(self.PHASE_ID),
            "phase_name": "In Progress",
            "fields": mock_fields,
        }

    async def test_required_only_filters_correctly(self, mock_phase_service):
        """Test get_phase_fields with required_only=True filters correctly."""
        mock_fields = [
            {
                "id": "status",
                "internal_id": "1",
                "uuid": "u1",
                "label": "Status",
                "type": "select",
                "required": True,
            },
            {
                "id": "notes",
                "internal_id": "2",
                "uuid": "u2",
                "label": "Notes",
                "type": "long_text",
                "required": False,
            },
            {
                "id": "resolution",
                "internal_id": "3",
                "uuid": "u3",
                "label": "Resolution",
                "type": "short_text",
                "required": True,
            },
        ]
        service, _ = mock_phase_service(
            {"id": str(self.PHASE_ID), "name": "Done", "fields": mock_fields}
        )

        result = await service.get_phase_fields(self.PHASE_ID, required_only=True)

        expected_fields = [
            {
                "id": "status",
                "internal_id": "1",
                "uuid": "u1",
                "label": "Status",
                "type": "select",
                "required": True,
            },
            {
                "id": "resolution",
                "internal_id": "3",
                "uuid": "u3",
                "label": "Resolution",
                "type": "short_text",
                "required": True,
            },
        ]
        assert result == {
            "phase_id": str(self.PHASE_ID),
            "phase_name": "Done",
            "fields": expected_fields,
        }

    @pytest.mark.parametrize(
        ("required_only", "fields", "phase_name", "expected_message"),
        [
            pytest.param(
                False,
                [],
                "Empty Phase",
                "This phase has no fields configured.",
                id="no_fields",
            ),
            pytest.param(
                True,
                [
                    {
                        "id": "notes",
                        "label": "Notes",
                        "type": "long_text",
                        "required": False,
                    },
                    {
                        "id": "priority",
                        "label": "Priority",
                        "type": "select",
                        "required": False,
                    },
                ],
                "Review",
                "This phase has no required fields.",
                id="all_optional_with_required_only",
            ),
        ],
    )
    async def test_empty_result_returns_message(
        self, mock_phase_service, required_only, fields, phase_name, expected_message
    ):
        """Test appropriate message when no fields match criteria."""
        service, _ = mock_phase_service(
            {"id": str(self.PHASE_ID), "name": phase_name, "fields": fields}
        )

        result = await service.get_phase_fields(
            self.PHASE_ID, required_only=required_only
        )

        assert result == {
            "phase_id": str(self.PHASE_ID),
            "phase_name": phase_name,
            "message": expected_message,
            "fields": [],
        }
