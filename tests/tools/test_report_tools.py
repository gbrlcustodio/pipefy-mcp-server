"""Tests for report MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.report_tools import ReportTools


@pytest.fixture
def mock_report_client():
    client = MagicMock(PipefyClient)
    client.get_pipe_reports = AsyncMock()
    client.get_pipe_report_columns = AsyncMock()
    client.get_pipe_report_filterable_fields = AsyncMock()
    client.get_organization_report = AsyncMock()
    client.get_organization_reports = AsyncMock()
    client.get_pipe_report_export = AsyncMock()
    client.get_organization_report_export = AsyncMock()
    client.create_pipe_report = AsyncMock()
    client.update_pipe_report = AsyncMock()
    client.delete_pipe_report = AsyncMock()
    client.create_organization_report = AsyncMock()
    client.update_organization_report = AsyncMock()
    client.delete_organization_report = AsyncMock()
    client.export_pipe_report = AsyncMock()
    client.export_organization_report = AsyncMock()
    client.export_pipe_audit_logs = AsyncMock()
    return client


@pytest.fixture
def report_mcp_server(mock_report_client):
    mcp = FastMCP("Report Tools Test")
    ReportTools.register(mcp, mock_report_client)
    return mcp


@pytest.fixture
def report_session(report_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        report_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_pipe_reports_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_pipe_reports.return_value = {
        "pipeReports": {
            "edges": [{"node": {"id": "r1", "name": "Weekly"}}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
    }

    async with report_session as session:
        result = await session.call_tool("get_pipe_reports", {"pipe_uuid": "uuid-123"})

    assert result.isError is False
    mock_report_client.get_pipe_reports.assert_awaited_once_with(
        "uuid-123", first=30, after=None, search=None, report_id=None, order=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["pipeReports"]["edges"][0]["node"]["name"] == "Weekly"


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_pipe_reports_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_pipe_reports.side_effect = TransportQueryError(
        "failed", errors=[{"message": "not allowed"}]
    )

    async with report_session as session:
        result = await session.call_tool("get_pipe_reports", {"pipe_uuid": "uuid-123"})

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "not allowed" in payload["error"]


class TestGetPipeReport:
    """Tests for ``get_pipe_report`` (single report via filtered ``get_pipe_reports``)."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("report_session", [None], indirect=True)
    async def test_get_pipe_report_success(
        self, report_session, mock_report_client, extract_payload
    ):
        mock_report_client.get_pipe_reports.return_value = {
            "pipeReports": {
                "edges": [
                    {
                        "node": {
                            "id": "r42",
                            "name": "Filtered",
                            "color": "#fff",
                        }
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }

        async with report_session as session:
            result = await session.call_tool(
                "get_pipe_report",
                {"pipe_uuid": "uuid-abc", "report_id": "r42"},
            )

        assert result.isError is False
        mock_report_client.get_pipe_reports.assert_awaited_once_with(
            "uuid-abc",
            first=1,
            report_id="r42",
        )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["data"]["pipeReport"]["id"] == "r42"
        assert payload["data"]["pipeReport"]["name"] == "Filtered"

    @pytest.mark.anyio
    @pytest.mark.parametrize("report_session", [None], indirect=True)
    async def test_get_pipe_report_not_found(
        self, report_session, mock_report_client, extract_payload
    ):
        mock_report_client.get_pipe_reports.return_value = {
            "pipeReports": {
                "edges": [],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }

        async with report_session as session:
            result = await session.call_tool(
                "get_pipe_report",
                {"pipe_uuid": "uuid-abc", "report_id": "missing"},
            )

        assert result.isError is False
        mock_report_client.get_pipe_reports.assert_awaited_once_with(
            "uuid-abc",
            first=1,
            report_id="missing",
        )
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "not found" in payload["error"].lower()
        assert "missing" in payload["error"]

    @pytest.mark.anyio
    @pytest.mark.parametrize("report_session", [None], indirect=True)
    async def test_get_pipe_report_graphql_error(
        self, report_session, mock_report_client, extract_payload
    ):
        mock_report_client.get_pipe_reports.side_effect = TransportQueryError(
            "failed", errors=[{"message": "pipe reports unavailable"}]
        )

        async with report_session as session:
            result = await session.call_tool(
                "get_pipe_report",
                {"pipe_uuid": "uuid-abc", "report_id": "r1"},
            )

        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "unavailable" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_pipe_report_columns_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_pipe_report_columns.return_value = {
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
                "options": [],
            },
        ]
    }

    async with report_session as session:
        result = await session.call_tool(
            "get_pipe_report_columns", {"pipe_uuid": "uuid-456"}
        )

    assert result.isError is False
    mock_report_client.get_pipe_report_columns.assert_awaited_once_with("uuid-456")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert len(payload["data"]["pipeReportColumns"]) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_pipe_report_filterable_fields_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_pipe_report_filterable_fields.return_value = {
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
                                "options": [],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    async with report_session as session:
        result = await session.call_tool(
            "get_pipe_report_filterable_fields", {"pipe_uuid": "uuid-789"}
        )

    assert result.isError is False
    mock_report_client.get_pipe_report_filterable_fields.assert_awaited_once_with(
        "uuid-789"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    inner = payload["data"]["pipeReportFilterableFields"][0]["list"][0]["list"][0]
    assert inner["type"] == "select"


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_report_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_organization_report.return_value = {
        "organizationReport": {
            "id": "or1",
            "name": "Org Overview",
            "cardCount": 100,
        }
    }

    async with report_session as session:
        result = await session.call_tool(
            "get_organization_report", {"report_id": "or1"}
        )

    assert result.isError is False
    mock_report_client.get_organization_report.assert_awaited_once_with("or1")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["organizationReport"]["name"] == "Org Overview"


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_reports_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_organization_reports.return_value = {
        "organizationReports": {
            "edges": [{"node": {"id": "or1", "name": "Report A"}}],
            "pageInfo": {"hasNextPage": True, "endCursor": "c2"},
        }
    }

    async with report_session as session:
        result = await session.call_tool(
            "get_organization_reports",
            {"organization_id": "org-1", "first": 10, "after": "c1"},
        )

    assert result.isError is False
    mock_report_client.get_organization_reports.assert_awaited_once_with(
        "org-1", first=10, after="c1"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["organizationReports"]["edges"][0]["node"]["id"] == "or1"


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_pipe_report_export_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_pipe_report_export.return_value = {
        "pipeReportExport": {
            "id": "exp1",
            "state": "done",
            "fileURL": "https://files.pipefy.com/export.csv",
        }
    }

    async with report_session as session:
        result = await session.call_tool(
            "get_pipe_report_export", {"export_id": "exp1"}
        )

    assert result.isError is False
    mock_report_client.get_pipe_report_export.assert_awaited_once_with("exp1")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["pipeReportExport"]["state"] == "done"


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_report_export_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_organization_report_export.return_value = {
        "organizationReportExport": {
            "id": "exp2",
            "state": "processing",
            "fileURL": None,
        }
    }

    async with report_session as session:
        result = await session.call_tool(
            "get_organization_report_export", {"export_id": "exp2"}
        )

    assert result.isError is False
    mock_report_client.get_organization_report_export.assert_awaited_once_with("exp2")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["data"]["organizationReportExport"]["state"] == "processing"


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_all_read_tools_have_readonly_hint(report_session):
    read_tool_names = [
        "get_pipe_reports",
        "get_pipe_report",
        "get_pipe_report_columns",
        "get_pipe_report_filterable_fields",
        "get_organization_report",
        "get_organization_reports",
        "get_pipe_report_export",
        "get_organization_report_export",
    ]
    async with report_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    for name in read_tool_names:
        tool = tool_map[name]
        assert tool.annotations is not None, f"{name} missing annotations"
        assert tool.annotations.readOnlyHint is True, (
            f"{name} should be readOnlyHint=True"
        )


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_pipe_report_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.create_pipe_report.return_value = {
        "createPipeReport": {"pipeReport": {"id": "r10", "name": "New Report"}}
    }

    async with report_session as session:
        result = await session.call_tool(
            "create_pipe_report",
            {"pipe_id": "123", "name": "New Report", "fields": ["title"]},
        )

    assert result.isError is False
    mock_report_client.create_pipe_report.assert_awaited_once_with(
        "123", "New Report", fields=["title"], filter=None, formulas=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["createPipeReport"]["pipeReport"]["id"] == "r10"


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_pipe_report_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.create_pipe_report.side_effect = TransportQueryError(
        "failed", errors=[{"message": "invalid pipe"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "create_pipe_report", {"pipe_id": "123", "name": "Bad"}
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "invalid pipe" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_pipe_report_graphql_error_with_debug(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.create_pipe_report.side_effect = TransportQueryError(
        '{"code": "PERMISSION_DENIED", "correlation_id": "corr-abc"}',
        errors=[
            {
                "message": "invalid pipe",
                "extensions": {"code": "PERMISSION_DENIED"},
            }
        ],
    )

    async with report_session as session:
        result = await session.call_tool(
            "create_pipe_report", {"pipe_id": "123", "name": "Bad", "debug": True}
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "invalid pipe" in payload["error"]
    assert "codes=" in payload["error"] or "correlation_id=" in payload["error"]
    assert "PERMISSION_DENIED" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_update_pipe_report_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.update_pipe_report.return_value = {
        "updatePipeReport": {"pipeReport": {"id": "r10", "name": "Updated"}}
    }

    async with report_session as session:
        result = await session.call_tool(
            "update_pipe_report",
            {"report_id": "r10", "name": "Updated", "color": "red"},
        )

    assert result.isError is False
    mock_report_client.update_pipe_report.assert_awaited_once_with(
        "r10",
        name="Updated",
        color="red",
        fields=None,
        filter=None,
        formulas=None,
        featured_field=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["updatePipeReport"]["pipeReport"]["name"] == "Updated"


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_delete_pipe_report_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.delete_pipe_report.return_value = {
        "deletePipeReport": {"success": True}
    }

    async with report_session as session:
        result = await session.call_tool(
            "delete_pipe_report", {"report_id": "r10", "confirm": True}
        )

    assert result.isError is False
    mock_report_client.delete_pipe_report.assert_awaited_once_with("r10")
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_organization_report_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.create_organization_report.return_value = {
        "createOrganizationReport": {
            "organizationReport": {"id": "or5", "name": "Cross-Pipe"}
        }
    }

    async with report_session as session:
        result = await session.call_tool(
            "create_organization_report",
            {
                "organization_id": "org-1",
                "name": "Cross-Pipe",
                "pipe_ids": ["p1", "p2"],
            },
        )

    assert result.isError is False
    mock_report_client.create_organization_report.assert_awaited_once_with(
        "org-1", "Cross-Pipe", ["p1", "p2"], fields=None, filter=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert (
        payload["result"]["createOrganizationReport"]["organizationReport"]["id"]
        == "or5"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_update_organization_report_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.update_organization_report.return_value = {
        "updateOrganizationReport": {
            "organizationReport": {"id": "or5", "name": "Updated Org"}
        }
    }

    async with report_session as session:
        result = await session.call_tool(
            "update_organization_report",
            {"report_id": "or5", "name": "Updated Org"},
        )

    assert result.isError is False
    mock_report_client.update_organization_report.assert_awaited_once_with(
        "or5", name="Updated Org", color=None, fields=None, filter=None, pipe_ids=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_delete_organization_report_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.delete_organization_report.return_value = {
        "deleteOrganizationReport": {"success": True}
    }

    async with report_session as session:
        result = await session.call_tool(
            "delete_organization_report", {"report_id": "or5", "confirm": True}
        )

    assert result.isError is False
    mock_report_client.delete_organization_report.assert_awaited_once_with("or5")
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_export_pipe_report_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.export_pipe_report.return_value = {
        "exportPipeReport": {
            "pipeReportExport": {"id": "exp1", "state": "processing"},
        }
    }

    async with report_session as session:
        result = await session.call_tool(
            "export_pipe_report",
            {"pipe_id": "p1", "pipe_report_id": "r1"},
        )

    assert result.isError is False
    mock_report_client.export_pipe_report.assert_awaited_once_with(
        "p1",
        "r1",
        sort_by=None,
        filter=None,
        columns=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert (
        payload["result"]["exportPipeReport"]["pipeReportExport"]["state"]
        == "processing"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_export_pipe_report_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.export_pipe_report.side_effect = TransportQueryError(
        "failed", errors=[{"message": "export denied"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "export_pipe_report",
            {"pipe_id": "p1", "pipe_report_id": "r1"},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "export denied" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_export_organization_report_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.export_organization_report.return_value = {
        "exportOrganizationReport": {
            "organizationReportExport": {"id": "exp-org-1", "state": "processing"},
        }
    }

    async with report_session as session:
        result = await session.call_tool(
            "export_organization_report",
            {
                "organization_id": 42,
                "organization_report_id": 7,
                "pipe_ids": [10, 11],
            },
        )

    assert result.isError is False
    mock_report_client.export_organization_report.assert_awaited_once_with(
        "42",
        organization_report_id="7",
        pipe_ids=["10", "11"],
        sort_by=None,
        filter=None,
        columns=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert (
        payload["result"]["exportOrganizationReport"]["organizationReportExport"][
            "state"
        ]
        == "processing"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_export_pipe_audit_logs_success(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.export_pipe_audit_logs.return_value = {
        "exportPipeAuditLogsReport": {"success": True},
    }

    async with report_session as session:
        result = await session.call_tool(
            "export_pipe_audit_logs",
            {"pipe_uuid": "uuid-abc", "search_term": "audit"},
        )

    assert result.isError is False
    mock_report_client.export_pipe_audit_logs.assert_awaited_once_with(
        "uuid-abc",
        search_term="audit",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["exportPipeAuditLogsReport"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_export_tools_are_not_readonly(report_session):
    export_tool_names = [
        "export_pipe_report",
        "export_organization_report",
        "export_pipe_audit_logs",
    ]
    async with report_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    for name in export_tool_names:
        tool = tool_map[name]
        assert tool.annotations is not None, f"{name} missing annotations"
        assert tool.annotations.readOnlyHint is False, (
            f"{name} should be readOnlyHint=False"
        )


## ---------------------------------------------------------------------------
## PipefyId coercion: int → str through MCP transport (mcporter mitigation)
## ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_report_coerces_int_report_id(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_organization_report.return_value = {
        "organizationReport": {"id": "500", "name": "Report"}
    }
    async with report_session as session:
        result = await session.call_tool("get_organization_report", {"report_id": 500})
    assert result.isError is False
    mock_report_client.get_organization_report.assert_awaited_once_with("500")
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_reports_coerces_int_organization_id(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_organization_reports.return_value = {
        "organizationReports": {
            "edges": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
    }
    async with report_session as session:
        result = await session.call_tool(
            "get_organization_reports", {"organization_id": 42}
        )
    assert result.isError is False
    mock_report_client.get_organization_reports.assert_awaited_once_with(
        "42", first=30, after=None
    )


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_pipe_report_export_coerces_int_export_id(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_pipe_report_export.return_value = {
        "pipeReportExport": {"id": "99", "state": "done", "fileURL": "https://x.com/f"}
    }
    async with report_session as session:
        result = await session.call_tool("get_pipe_report_export", {"export_id": 99})
    assert result.isError is False
    mock_report_client.get_pipe_report_export.assert_awaited_once_with("99")
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_report_export_coerces_int_export_id(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_organization_report_export.return_value = {
        "organizationExport": {"id": "88", "state": "done"}
    }
    async with report_session as session:
        result = await session.call_tool(
            "get_organization_report_export", {"export_id": 88}
        )
    assert result.isError is False
    mock_report_client.get_organization_report_export.assert_awaited_once_with("88")


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_pipe_report_coerces_int_pipe_id(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.create_pipe_report.return_value = {
        "createPipeReport": {"pipeReport": {"id": "r1"}}
    }
    async with report_session as session:
        result = await session.call_tool(
            "create_pipe_report", {"pipe_id": 301, "name": "Report"}
        )
    assert result.isError is False
    mock_report_client.create_pipe_report.assert_awaited_once_with(
        "301", "Report", fields=None, filter=None, formulas=None
    )


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_update_pipe_report_coerces_int_report_id(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.update_pipe_report.return_value = {
        "updatePipeReport": {"pipeReport": {"id": "200"}}
    }
    async with report_session as session:
        result = await session.call_tool(
            "update_pipe_report", {"report_id": 200, "name": "Updated"}
        )
    assert result.isError is False
    mock_report_client.update_pipe_report.assert_awaited_once_with(
        "200",
        name="Updated",
        color=None,
        fields=None,
        filter=None,
        formulas=None,
        featured_field=None,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_export_pipe_report_coerces_int_ids(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.export_pipe_report.return_value = {
        "exportPipeReport": {"pipeReportExport": {"id": "e1", "state": "processing"}}
    }
    async with report_session as session:
        result = await session.call_tool(
            "export_pipe_report", {"pipe_id": 301, "pipe_report_id": 777}
        )
    assert result.isError is False
    mock_report_client.export_pipe_report.assert_awaited_once_with(
        "301",
        "777",
        sort_by=None,
        filter=None,
        columns=None,
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_organization_report_coerces_int_organization_id(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.create_organization_report.return_value = {
        "createOrganizationReport": {"organizationReport": {"id": "or1"}}
    }
    async with report_session as session:
        result = await session.call_tool(
            "create_organization_report",
            {"organization_id": 42, "name": "Org Report", "pipe_ids": ["10"]},
        )
    assert result.isError is False
    mock_report_client.create_organization_report.assert_awaited_once_with(
        "42", "Org Report", ["10"], fields=None, filter=None
    )


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_update_organization_report_coerces_int_report_id(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.update_organization_report.return_value = {
        "updateOrganizationReport": {"organizationReport": {"id": "300"}}
    }
    async with report_session as session:
        result = await session.call_tool(
            "update_organization_report", {"report_id": 300, "name": "Renamed"}
        )
    assert result.isError is False
    mock_report_client.update_organization_report.assert_awaited_once_with(
        "300", name="Renamed", color=None, fields=None, filter=None, pipe_ids=None
    )


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_pipe_reports_coerces_int_report_id_filter(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_pipe_reports.return_value = {
        "pipeReports": {
            "edges": [{"node": {"id": "55", "name": "R"}}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }
    }
    async with report_session as session:
        result = await session.call_tool(
            "get_pipe_reports", {"pipe_uuid": "uuid-x", "report_id": 55}
        )
    assert result.isError is False
    mock_report_client.get_pipe_reports.assert_awaited_once_with(
        "uuid-x", first=30, after=None, search=None, report_id="55", order=None
    )


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_delete_tools_have_destructive_hint(report_session):
    async with report_session as session:
        listed = await session.list_tools()

    tool_map = {t.name: t for t in listed.tools}
    for name in ["delete_pipe_report", "delete_organization_report"]:
        tool = tool_map[name]
        assert tool.annotations is not None, f"{name} missing annotations"
        assert tool.annotations.destructiveHint is True, (
            f"{name} should be destructiveHint=True"
        )


## ---------------------------------------------------------------------------
## _blank_field_error validation: non-string and blank string inputs
## ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_pipe_reports_blank_pipe_uuid(report_session, extract_payload):
    async with report_session as session:
        result = await session.call_tool("get_pipe_reports", {"pipe_uuid": ""})

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "non-empty" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_report_blank_report_id(report_session, extract_payload):
    async with report_session as session:
        result = await session.call_tool("get_organization_report", {"report_id": ""})

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "non-empty" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_reports_blank_organization_id(
    report_session, extract_payload
):
    async with report_session as session:
        result = await session.call_tool(
            "get_organization_reports", {"organization_id": ""}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "non-empty" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_pipe_report_export_blank_export_id(report_session, extract_payload):
    async with report_session as session:
        result = await session.call_tool("get_pipe_report_export", {"export_id": ""})

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "non-empty" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_report_export_blank_export_id(
    report_session, extract_payload
):
    async with report_session as session:
        result = await session.call_tool(
            "get_organization_report_export", {"export_id": ""}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "non-empty" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_pipe_report_blank_pipe_id(report_session, extract_payload):
    async with report_session as session:
        result = await session.call_tool(
            "create_pipe_report", {"pipe_id": "", "name": "x"}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "pipe_id" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_pipe_report_blank_name(report_session, extract_payload):
    async with report_session as session:
        result = await session.call_tool(
            "create_pipe_report", {"pipe_id": "x", "name": ""}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "name" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_update_pipe_report_blank_report_id(report_session, extract_payload):
    async with report_session as session:
        result = await session.call_tool("update_pipe_report", {"report_id": ""})

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "report_id" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_organization_report_blank_organization_id(
    report_session, extract_payload
):
    async with report_session as session:
        result = await session.call_tool(
            "create_organization_report",
            {"organization_id": "", "name": "x", "pipe_ids": ["1"]},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "organization_id" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_organization_report_blank_name(report_session, extract_payload):
    async with report_session as session:
        result = await session.call_tool(
            "create_organization_report",
            {"organization_id": "x", "name": "", "pipe_ids": ["1"]},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "name" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_update_organization_report_blank_report_id(
    report_session, extract_payload
):
    async with report_session as session:
        result = await session.call_tool(
            "update_organization_report", {"report_id": ""}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "report_id" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_export_pipe_report_blank_pipe_id(report_session, extract_payload):
    async with report_session as session:
        result = await session.call_tool(
            "export_pipe_report", {"pipe_id": "", "pipe_report_id": "x"}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "pipe_id" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_export_pipe_report_blank_pipe_report_id(report_session, extract_payload):
    async with report_session as session:
        result = await session.call_tool(
            "export_pipe_report", {"pipe_id": "x", "pipe_report_id": ""}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "pipe_report_id" in payload["error"]


## ---------------------------------------------------------------------------
## first < 1 validation
## ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_pipe_reports_first_less_than_one(report_session, extract_payload):
    async with report_session as session:
        result = await session.call_tool(
            "get_pipe_reports", {"pipe_uuid": "uuid-1", "first": 0}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "positive integer" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_reports_first_less_than_one(
    report_session, extract_payload
):
    async with report_session as session:
        result = await session.call_tool(
            "get_organization_reports", {"organization_id": "org-1", "first": 0}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "positive integer" in payload["error"]


## ---------------------------------------------------------------------------
## pipe_ids validation in create_organization_report
## ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_organization_report_empty_pipe_ids(
    report_session, extract_payload
):
    async with report_session as session:
        result = await session.call_tool(
            "create_organization_report",
            {"organization_id": "org-1", "name": "Report", "pipe_ids": []},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "pipe_ids" in payload["error"]


## ---------------------------------------------------------------------------
## export_organization_report: organization_id < 1 validation
## ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_export_organization_report_organization_id_less_than_one(
    report_session, extract_payload
):
    async with report_session as session:
        result = await session.call_tool(
            "export_organization_report",
            {"organization_id": 0, "pipe_ids": [1]},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "positive integer" in payload["error"]


## ---------------------------------------------------------------------------
## GraphQL error paths (TransportQueryError)
## ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_report_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_organization_report.side_effect = TransportQueryError(
        "failed", errors=[{"message": "org not found"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "get_organization_report", {"report_id": "or1"}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "org not found" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_reports_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_organization_reports.side_effect = TransportQueryError(
        "failed", errors=[{"message": "access denied"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "get_organization_reports", {"organization_id": "org-1"}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "access denied" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_pipe_report_export_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_pipe_report_export.side_effect = TransportQueryError(
        "failed", errors=[{"message": "export not found"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "get_pipe_report_export", {"export_id": "exp1"}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "export not found" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_get_organization_report_export_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.get_organization_report_export.side_effect = TransportQueryError(
        "failed", errors=[{"message": "export error"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "get_organization_report_export", {"export_id": "exp2"}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "export error" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_update_pipe_report_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.update_pipe_report.side_effect = TransportQueryError(
        "failed", errors=[{"message": "update denied"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "update_pipe_report", {"report_id": "r10", "name": "Bad"}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "update denied" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_delete_pipe_report_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.delete_pipe_report.side_effect = TransportQueryError(
        "failed", errors=[{"message": "delete denied"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "delete_pipe_report", {"report_id": "r10", "confirm": True}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "delete denied" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_create_organization_report_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.create_organization_report.side_effect = TransportQueryError(
        "failed", errors=[{"message": "org create failed"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "create_organization_report",
            {"organization_id": "org-1", "name": "Report", "pipe_ids": ["p1"]},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "org create failed" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_update_organization_report_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.update_organization_report.side_effect = TransportQueryError(
        "failed", errors=[{"message": "org update failed"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "update_organization_report", {"report_id": "or5", "name": "Bad"}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "org update failed" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_delete_organization_report_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.delete_organization_report.side_effect = TransportQueryError(
        "failed", errors=[{"message": "org delete failed"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "delete_organization_report", {"report_id": "or5", "confirm": True}
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "org delete failed" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("report_session", [None], indirect=True)
async def test_export_organization_report_graphql_error(
    report_session, mock_report_client, extract_payload
):
    mock_report_client.export_organization_report.side_effect = TransportQueryError(
        "failed", errors=[{"message": "export org failed"}]
    )

    async with report_session as session:
        result = await session.call_tool(
            "export_organization_report",
            {"organization_id": 42, "pipe_ids": [10]},
        )

    payload = extract_payload(result)
    assert payload["success"] is False
    assert "export org failed" in payload["error"]
