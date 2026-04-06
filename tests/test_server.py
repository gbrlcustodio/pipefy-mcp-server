from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.server import mcp as mcp_server
from pipefy_mcp.server import run_server
from pipefy_mcp.settings import PipefySettings, Settings


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def client_session():
    return create_client_session(
        mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    )


_MINIMAL_PIPEFY_SETTINGS = Settings(
    pipefy=PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://api.pipefy.com/oauth/token",
        oauth_client="test-client",
        oauth_secret="test-secret",
    )
)


@pytest.mark.anyio
async def test_register_tools(client_session):
    expected_tool_names = [
        "add_card_comment",
        "clone_pipe",
        "create_ai_agent",
        "create_ai_automation",
        "create_automation",
        "create_card",
        "create_card_relation",
        "create_field_condition",
        "create_label",
        "create_organization_report",
        "create_phase",
        "create_phase_field",
        "create_pipe",
        "create_pipe_relation",
        "create_pipe_report",
        "create_table",
        "create_table_field",
        "create_table_record",
        "create_webhook",
        "delete_ai_agent",
        "toggle_ai_agent_status",
        "delete_automation",
        "delete_card",
        "delete_comment",
        "delete_field_condition",
        "delete_label",
        "delete_organization_report",
        "delete_phase",
        "delete_phase_field",
        "delete_pipe",
        "delete_pipe_relation",
        "delete_pipe_report",
        "delete_table",
        "delete_table_field",
        "delete_table_record",
        "delete_webhook",
        "execute_graphql",
        "export_automation_jobs",
        "export_organization_report",
        "export_pipe_audit_logs",
        "export_pipe_report",
        "fill_card_phase_fields",
        "find_cards",
        "find_records",
        "get_agents_usage",
        "get_ai_agent",
        "get_ai_agent_log_details",
        "get_ai_agent_logs",
        "get_ai_agents",
        "get_ai_credit_usage",
        "get_automation",
        "get_automation_actions",
        "get_automation_events",
        "get_automation_jobs_export",
        "get_automation_jobs_export_csv",
        "get_automation_logs",
        "get_automation_logs_by_repo",
        "get_automations",
        "get_automations_usage",
        "get_card",
        "get_card_inbox_emails",
        "get_cards",
        "get_email_templates",
        "get_organization",
        "get_organization_report",
        "get_organization_report_export",
        "get_organization_reports",
        "get_phase_fields",
        "get_pipe",
        "get_pipe_members",
        "get_pipe_relations",
        "get_pipe_report_columns",
        "get_pipe_report_export",
        "get_pipe_report_filterable_fields",
        "get_pipe_reports",
        "get_start_form_fields",
        "get_table",
        "get_table_record",
        "get_table_records",
        "get_tables",
        "get_table_relations",
        "introspect_mutation",
        "introspect_query",
        "introspect_type",
        "invite_members",
        "move_card_to_phase",
        "remove_member_from_pipe",
        "search_pipes",
        "search_schema",
        "search_tables",
        "send_email_with_template",
        "send_inbox_email",
        "simulate_automation",
        "set_role",
        "set_table_record_field_value",
        "update_ai_agent",
        "update_ai_automation",
        "update_automation",
        "update_card",
        "update_card_field",
        "update_comment",
        "update_field_condition",
        "update_label",
        "update_organization_report",
        "update_phase",
        "update_phase_field",
        "update_pipe",
        "update_pipe_relation",
        "update_pipe_report",
        "update_table",
        "update_table_field",
        "update_table_record",
        "validate_ai_agent_behaviors",
    ]

    with patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS):
        async with client_session as session:
            result = await session.list_tools()
            actual_tool_names = [tool.name for tool in result.tools]

            assert sorted(expected_tool_names) == sorted(actual_tool_names), (
                "Expected create_card to be available"
            )


@pytest.mark.unit
def test_run_server_calls_logger_and_mcp_run():
    """run_server logs and calls mcp.run()."""
    with (
        patch("pipefy_mcp.server.logger") as mock_logger,
        patch("pipefy_mcp.server.mcp") as mock_mcp,
    ):
        run_server()
        mock_logger.info.assert_called()
        mock_mcp.run.assert_called_once()


@pytest.mark.unit
@pytest.mark.anyio
async def test_lifespan_logs_error_when_initialization_raises():
    """When lifespan initialization raises, logger.exception runs and the error propagates."""
    from pipefy_mcp.server import lifespan

    app = FastMCP("test")
    with (
        patch("pipefy_mcp.server.settings", _MINIMAL_PIPEFY_SETTINGS),
        patch("pipefy_mcp.server.ServicesContainer.get_instance") as mock_get_instance,
        patch("pipefy_mcp.server.logger") as mock_logger,
    ):
        mock_container = MagicMock()
        mock_container.initialize_services.side_effect = ValueError("init failed")
        mock_get_instance.return_value = mock_container

        with pytest.raises(ValueError, match="init failed"):
            async with lifespan(app):
                pass

        mock_logger.exception.assert_called_once()
        call_msg = mock_logger.exception.call_args[0][0]
        assert "Fatal error during server lifespan" in call_msg
