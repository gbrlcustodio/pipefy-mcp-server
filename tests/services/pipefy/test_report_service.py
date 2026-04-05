"""Unit tests for ReportService."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.services.pipefy.queries.report_queries import (
    CREATE_ORGANIZATION_REPORT_MUTATION,
    CREATE_PIPE_REPORT_MUTATION,
    DELETE_ORGANIZATION_REPORT_MUTATION,
    DELETE_PIPE_REPORT_MUTATION,
    EXPORT_ORGANIZATION_REPORT_MUTATION,
    EXPORT_PIPE_AUDIT_LOGS_MUTATION,
    EXPORT_PIPE_REPORT_MUTATION,
    GET_ORGANIZATION_REPORT_EXPORT_QUERY,
    GET_ORGANIZATION_REPORT_QUERY,
    GET_ORGANIZATION_REPORTS_QUERY,
    GET_PIPE_REPORT_COLUMNS_QUERY,
    GET_PIPE_REPORT_EXPORT_QUERY,
    GET_PIPE_REPORT_FILTERABLE_FIELDS_QUERY,
    GET_PIPE_REPORTS_QUERY,
    UPDATE_ORGANIZATION_REPORT_MUTATION,
    UPDATE_PIPE_REPORT_MUTATION,
)
from pipefy_mcp.services.pipefy.report_service import ReportService
from pipefy_mcp.settings import PipefySettings


@pytest.fixture
def mock_settings():
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value):
    service = ReportService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_reports_success(mock_settings):
    payload = {
        "pipeReports": {
            "edges": [
                {
                    "node": {
                        "id": "r1",
                        "name": "Weekly Report",
                        "color": "blue",
                        "fields": ["title", "status"],
                        "filter": None,
                        "sortBy": {"direction": "asc", "field": "title"},
                        "createdAt": "2025-01-01T00:00:00Z",
                        "lastUpdatedAt": "2025-06-01T00:00:00Z",
                    }
                }
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": "abc123"},
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_pipe_reports("uuid-123")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is GET_PIPE_REPORTS_QUERY
    assert variables["pipeUuid"] == "uuid-123"
    assert variables["first"] == 30
    assert result["pipeReports"]["edges"][0]["node"]["name"] == "Weekly Report"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_reports_with_optional_params(mock_settings):
    payload = {
        "pipeReports": {
            "edges": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
    }
    service = _make_service(mock_settings, payload)
    await service.get_pipe_reports(
        "uuid-123",
        first=10,
        after="cursor",
        search="weekly",
        report_id="r5",
        order={"field": "name", "direction": "asc"},
    )

    variables = service.execute_query.call_args[0][1]
    assert variables["first"] == 10
    assert variables["after"] == "cursor"
    assert variables["search"] == "weekly"
    assert variables["reportId"] == "r5"
    assert variables["order"] == {"field": "name", "direction": "asc"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_reports_transport_error(mock_settings):
    service = ReportService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_pipe_reports("uuid-123")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_report_columns_success(mock_settings):
    payload = {
        "pipeReportColumns": [
            {
                "name": "title",
                "label": "Title",
                "type": "string",
                "visible": True,
                "archived": None,
                "options": [],
            },
            {
                "name": "status",
                "label": "Status",
                "type": "select",
                "visible": True,
                "archived": None,
                "options": [{"id": "1", "name": "Open"}],
            },
        ]
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_pipe_report_columns("uuid-456")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_PIPE_REPORT_COLUMNS_QUERY
    assert variables == {"pipeUuid": "uuid-456"}
    assert len(result["pipeReportColumns"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_report_filterable_fields_success(mock_settings):
    payload = {
        "pipeReportFilterableFields": [
            {
                "title": "General",
                "list": [
                    {
                        "label": "Card Attributes",
                        "list": [
                            {
                                "name": "status",
                                "label": "Status",
                                "type": "select",
                                "options": [{"id": "1", "name": "Open"}],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_pipe_report_filterable_fields("uuid-789")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_PIPE_REPORT_FILTERABLE_FIELDS_QUERY
    assert variables == {"pipeUuid": "uuid-789"}
    inner = result["pipeReportFilterableFields"][0]["list"][0]["list"][0]
    assert inner["type"] == "select"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_organization_report_success(mock_settings):
    payload = {
        "organizationReport": {
            "id": "or1",
            "name": "Org Overview",
            "cardCount": 100,
            "color": "green",
            "fields": ["title"],
            "filter": None,
            "repos": [{"id": "p1", "name": "Pipe A"}],
            "sortBy": {"direction": "desc", "field": "created_at"},
            "createdAt": "2025-01-01T00:00:00Z",
            "lastUpdatedAt": "2025-06-01T00:00:00Z",
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_organization_report("or1")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_ORGANIZATION_REPORT_QUERY
    assert variables == {"id": "or1"}
    assert result["organizationReport"]["name"] == "Org Overview"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_organization_reports_success(mock_settings):
    payload = {
        "organizationReports": {
            "edges": [
                {
                    "node": {
                        "id": "or1",
                        "name": "Report A",
                        "cardCount": 10,
                        "color": "red",
                    }
                },
                {
                    "node": {
                        "id": "or2",
                        "name": "Report B",
                        "cardCount": 20,
                        "color": "blue",
                    }
                },
            ],
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor-2"},
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_organization_reports("org-1", first=5, after="cursor-1")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_ORGANIZATION_REPORTS_QUERY
    assert variables["organizationId"] == "org-1"
    assert variables["first"] == 5
    assert variables["after"] == "cursor-1"
    assert len(result["organizationReports"]["edges"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_report_export_success(mock_settings):
    payload = {
        "pipeReportExport": {
            "id": "exp1",
            "state": "done",
            "fileURL": "https://files.pipefy.com/export.csv",
            "startedAt": "2025-06-01T00:00:00Z",
            "finishedAt": "2025-06-01T00:01:00Z",
            "requestedBy": {"id": "u1", "name": "Admin"},
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_pipe_report_export("exp1")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_PIPE_REPORT_EXPORT_QUERY
    assert variables == {"id": "exp1"}
    assert result["pipeReportExport"]["state"] == "done"
    assert (
        result["pipeReportExport"]["fileURL"] == "https://files.pipefy.com/export.csv"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_organization_report_export_success(mock_settings):
    payload = {
        "organizationReportExport": {
            "id": "exp2",
            "state": "processing",
            "fileURL": None,
            "startedAt": "2025-06-01T00:00:00Z",
            "finishedAt": None,
            "requestedBy": {"id": "u2", "name": "User"},
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_organization_report_export("exp2")

    query, variables = service.execute_query.call_args[0]
    assert query is GET_ORGANIZATION_REPORT_EXPORT_QUERY
    assert variables == {"id": "exp2"}
    assert result["organizationReportExport"]["state"] == "processing"
    assert result["organizationReportExport"]["fileURL"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_report_success(mock_settings):
    payload = {"createPipeReport": {"pipeReport": {"id": "r10", "name": "New Report"}}}
    service = _make_service(mock_settings, payload)
    result = await service.create_pipe_report(
        "123", "New Report", fields=["title", "status"]
    )

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_PIPE_REPORT_MUTATION
    assert variables["input"]["pipeId"] == 123
    assert variables["input"]["name"] == "New Report"
    assert variables["input"]["fields"] == ["title", "status"]
    assert result["createPipeReport"]["pipeReport"]["id"] == "r10"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_report_minimal(mock_settings):
    payload = {"createPipeReport": {"pipeReport": {"id": "r11", "name": "Minimal"}}}
    service = _make_service(mock_settings, payload)
    result = await service.create_pipe_report("456", "Minimal")

    variables = service.execute_query.call_args[0][1]
    assert variables["input"] == {"pipeId": 456, "name": "Minimal"}
    assert result["createPipeReport"]["pipeReport"]["name"] == "Minimal"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipe_report_transport_error(mock_settings):
    service = ReportService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.create_pipe_report("123", "Report")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_report_success(mock_settings):
    payload = {"updatePipeReport": {"pipeReport": {"id": "10", "name": "Updated"}}}
    service = _make_service(mock_settings, payload)
    result = await service.update_pipe_report(
        "10", name="Updated", color="red", fields=["title"]
    )

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_PIPE_REPORT_MUTATION
    assert variables["input"]["id"] == 10
    assert variables["input"]["name"] == "Updated"
    assert variables["input"]["color"] == "red"
    assert variables["input"]["fields"] == ["title"]
    assert result["updatePipeReport"]["pipeReport"]["name"] == "Updated"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_report_skips_none_values(mock_settings):
    payload = {"updatePipeReport": {"pipeReport": {"id": "10", "name": "Same"}}}
    service = _make_service(mock_settings, payload)
    await service.update_pipe_report("10", name="Same")

    variables = service.execute_query.call_args[0][1]
    assert variables["input"] == {"id": 10, "name": "Same"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_pipe_report_success(mock_settings):
    payload = {"deletePipeReport": {"success": True}}
    service = _make_service(mock_settings, payload)
    result = await service.delete_pipe_report("10")

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_PIPE_REPORT_MUTATION
    assert variables["input"] == {"id": 10}
    assert result["deletePipeReport"]["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_organization_report_success(mock_settings):
    payload = {
        "createOrganizationReport": {
            "organizationReport": {"id": "5", "name": "Cross-Pipe"}
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.create_organization_report(
        "100", "Cross-Pipe", ["200", "300"], fields=["title"]
    )

    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_ORGANIZATION_REPORT_MUTATION
    assert variables["input"]["organizationId"] == 100
    assert variables["input"]["name"] == "Cross-Pipe"
    assert variables["input"]["pipeIds"] == [200, 300]
    assert variables["input"]["fields"] == ["title"]
    assert result["createOrganizationReport"]["organizationReport"]["id"] == "5"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_organization_report_success(mock_settings):
    payload = {
        "updateOrganizationReport": {
            "organizationReport": {"id": "5", "name": "Updated Org"}
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.update_organization_report(
        "5", name="Updated Org", pipe_ids=["200", "400"]
    )

    query, variables = service.execute_query.call_args[0]
    assert query is UPDATE_ORGANIZATION_REPORT_MUTATION
    assert variables["input"]["id"] == 5
    assert variables["input"]["name"] == "Updated Org"
    assert variables["input"]["pipeIds"] == [200, 400]
    assert (
        result["updateOrganizationReport"]["organizationReport"]["name"]
        == "Updated Org"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_organization_report_success(mock_settings):
    payload = {"deleteOrganizationReport": {"success": True}}
    service = _make_service(mock_settings, payload)
    result = await service.delete_organization_report("5")

    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_ORGANIZATION_REPORT_MUTATION
    assert variables["input"] == {"id": 5}
    assert result["deleteOrganizationReport"]["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_pipe_report_success(mock_settings):
    payload = {
        "exportPipeReport": {"pipeReportExport": {"id": "exp1", "state": "processing"}}
    }
    service = _make_service(mock_settings, payload)
    result = await service.export_pipe_report("100", "200")

    query, variables = service.execute_query.call_args[0]
    assert query is EXPORT_PIPE_REPORT_MUTATION
    assert variables["input"] == {"pipeId": 100, "pipeReportId": 200}
    assert result["exportPipeReport"]["pipeReportExport"]["state"] == "processing"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_pipe_report_transport_error(mock_settings):
    service = ReportService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.export_pipe_report("100", "200")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_organization_report_success(mock_settings):
    payload = {
        "exportOrganizationReport": {
            "organizationReportExport": {"id": "exp-org-1", "state": "processing"}
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.export_organization_report(
        42, organization_report_id=7, pipe_ids=[10, 11]
    )

    query, variables = service.execute_query.call_args[0]
    assert query is EXPORT_ORGANIZATION_REPORT_MUTATION
    assert variables["input"] == {
        "organizationId": 42,
        "organizationReportId": 7,
        "pipeIds": [10, 11],
    }
    assert (
        result["exportOrganizationReport"]["organizationReportExport"]["state"]
        == "processing"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_pipe_audit_logs_success(mock_settings):
    payload = {"exportPipeAuditLogsReport": {"success": True}}
    service = _make_service(mock_settings, payload)
    result = await service.export_pipe_audit_logs("uuid-abc", search_term="audit")

    query, variables = service.execute_query.call_args[0]
    assert query is EXPORT_PIPE_AUDIT_LOGS_MUTATION
    assert variables["input"] == {"pipeUuid": "uuid-abc", "searchTerm": "audit"}
    assert result["exportPipeAuditLogsReport"]["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pipe_report_columns_transport_error(mock_settings):
    service = ReportService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_pipe_report_columns("uuid-456")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_pipe_report_transport_error(mock_settings):
    service = ReportService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "gone"}])
    )
    with pytest.raises(TransportQueryError):
        await service.update_pipe_report("10", name="N")
