"""Tests for NOT_FOUND / INVALID_ARGUMENTS enrichment in graphql_error_helpers."""

import pytest

from pipefy_mcp.tools.graphql_error_helpers import (
    enrich_ambiguous_access_error,
    enrich_invalid_arguments_error,
    enrich_not_found_error,
    handle_tool_graphql_error,
)
from pipefy_mcp.tools.tool_error_envelope import tool_error_message


class _FakeGraphQLError(Exception):
    """Mimics ``gql.transport.exceptions.TransportQueryError`` shape."""

    def __init__(self, code: str | None, message: str):
        super().__init__(message)
        self._raw_message = message
        error_item: dict = {"message": message}
        if code is not None:
            error_item["extensions"] = {"code": code}
        self.errors = [error_item]

    def __str__(self) -> str:
        return self._raw_message


def _build_graphql_exc(code: str | None, message: str) -> _FakeGraphQLError:
    return _FakeGraphQLError(code, message)


class TestEnrichNotFoundError:
    def test_not_found_enriches_pipe_error(self):
        exc = _build_graphql_exc("NOT_FOUND", "Pipe not found")
        result = enrich_not_found_error(exc, resource_kind="pipe", resource_id="42")
        assert result is not None
        assert "Pipe not found" in result
        assert "42" in result
        assert "search_pipes" in result

    def test_not_found_string_based_fallback(self):
        exc = _build_graphql_exc(None, "Record not found for id 99")
        result = enrich_not_found_error(exc, resource_kind="card")
        assert result is not None
        assert "find_cards" in result

    def test_not_found_returns_none_for_unrelated(self):
        exc = _build_graphql_exc(
            "PERMISSION_DENIED", "You do not have permission to access this pipe"
        )
        result = enrich_not_found_error(exc, resource_kind="pipe", resource_id="42")
        assert result is None

    def test_not_found_unknown_resource_kind(self):
        exc = _build_graphql_exc("NOT_FOUND", "Banana not found")
        result = enrich_not_found_error(exc, resource_kind="banana")
        assert result is not None
        assert result.endswith("Verify the ID and try again.")

    def test_not_found_omits_id_clause_when_missing(self):
        exc = _build_graphql_exc("NOT_FOUND", "Pipe not found")
        result = enrich_not_found_error(exc, resource_kind="pipe")
        assert result is not None
        assert "(ID:" not in result
        assert "search_pipes" in result

    def test_not_found_humanizes_snake_case(self):
        exc = _build_graphql_exc("NOT_FOUND", "Record not found")
        result = enrich_not_found_error(
            exc, resource_kind="table_record", resource_id="rec_1"
        )
        assert result is not None
        assert "Table record not found" in result
        assert "find_records" in result


class TestEnrichAmbiguousAccessError:
    def test_permission_denied_rewritten_with_ambiguity_hint(self):
        exc = _build_graphql_exc("PERMISSION_DENIED", "Permission denied")
        result = enrich_ambiguous_access_error(
            exc, resource_kind="pipe", resource_id="99999999"
        )
        assert result is not None
        assert "99999999" in result
        assert "may not exist" in result
        assert "may lack access" in result
        assert "search_pipes" in result
        assert "get_pipe_members" in result

    def test_returns_none_when_not_permission_denied(self):
        exc = _build_graphql_exc("NOT_FOUND", "Pipe not found")
        result = enrich_ambiguous_access_error(exc, resource_kind="pipe")
        assert result is None

    def test_returns_none_when_code_absent(self):
        exc = _build_graphql_exc(None, "Some other error")
        result = enrich_ambiguous_access_error(exc, resource_kind="pipe")
        assert result is None

    def test_omits_id_clause_when_missing(self):
        exc = _build_graphql_exc("PERMISSION_DENIED", "Permission denied")
        result = enrich_ambiguous_access_error(exc, resource_kind="webhook")
        assert result is not None
        assert "(ID:" not in result
        assert "get_webhooks" in result

    def test_unknown_resource_kind_falls_back_to_generic_hint(self):
        exc = _build_graphql_exc("PERMISSION_DENIED", "Permission denied")
        result = enrich_ambiguous_access_error(
            exc, resource_kind="banana", resource_id="x"
        )
        assert result is not None
        assert "Verify the ID and try again." in result

    @pytest.mark.parametrize(
        "kind",
        [
            "pipe",
            "phase",
            "phase_field",
            "card",
            "label",
            "pipe_report",
            "pipe_relation",
            "field_condition",
            "start_form_field",
        ],
    )
    def test_pipe_centric_kinds_include_membership_hint(self, kind):
        exc = _build_graphql_exc("PERMISSION_DENIED", "Permission denied")
        result = enrich_ambiguous_access_error(exc, resource_kind=kind)
        assert result is not None
        assert "get_pipe_members" in result

    @pytest.mark.parametrize(
        "kind",
        [
            "automation",
            "ai_automation",
            "table",
            "table_record",
            "webhook",
            "ai_agent",
            "ai_agent_log",
            "organization",
            "organization_report",
            "email_template",
        ],
    )
    def test_non_pipe_centric_kinds_omit_membership_hint(self, kind):
        exc = _build_graphql_exc("PERMISSION_DENIED", "Permission denied")
        result = enrich_ambiguous_access_error(exc, resource_kind=kind)
        assert result is not None
        assert "get_pipe_members" not in result
        assert "may not exist" in result


class TestEnrichInvalidArgumentsError:
    def test_invalid_arguments_adds_hint(self):
        exc = _build_graphql_exc("BAD_USER_INPUT", "Argument 'phaseFieldId' is invalid")
        hint = "Use 'get_phase_fields' to list valid field IDs."
        result = enrich_invalid_arguments_error(exc, hint=hint)
        assert result is not None
        assert hint in result

    def test_invalid_arguments_default_hint(self):
        exc = _build_graphql_exc("BAD_USER_INPUT", "Field 'x' invalid")
        result = enrich_invalid_arguments_error(exc)
        assert result is not None
        assert "docstring" in result

    def test_invalid_arguments_returns_none_for_unrelated(self):
        exc = _build_graphql_exc("NOT_FOUND", "Pipe not found")
        result = enrich_invalid_arguments_error(exc, hint="any hint")
        assert result is None


class TestHandleToolGraphqlErrorIntegration:
    def test_preserves_legacy_when_no_kind_passed(self):
        exc = _build_graphql_exc("NOT_FOUND", "Pipe not found")
        payload = handle_tool_graphql_error(exc, "Failed")
        message = tool_error_message(payload)
        assert message == "Pipe not found"
        assert "search_pipes" not in message
        assert payload["error"]["code"] == "NOT_FOUND"

    def test_enriches_when_kind_passed(self):
        exc = _build_graphql_exc("NOT_FOUND", "Pipe not found")
        payload = handle_tool_graphql_error(
            exc, "Failed", resource_kind="pipe", resource_id="42"
        )
        message = tool_error_message(payload)
        assert "Pipe not found (ID: 42)" in message
        assert "search_pipes" in message
        assert payload["error"]["code"] == "NOT_FOUND"

    def test_enriches_invalid_arguments_when_hint_passed(self):
        exc = _build_graphql_exc("BAD_USER_INPUT", "Invalid argument 'field_id'")
        payload = handle_tool_graphql_error(
            exc,
            "Failed",
            invalid_args_hint="Use 'get_phase_fields' to list valid field IDs.",
        )
        message = tool_error_message(payload)
        assert "get_phase_fields" in message
        assert payload["error"]["code"] == "BAD_USER_INPUT"

    def test_not_found_takes_precedence_over_invalid_args(self):
        exc = _build_graphql_exc("NOT_FOUND", "Pipe not found")
        payload = handle_tool_graphql_error(
            exc,
            "Failed",
            resource_kind="pipe",
            resource_id="42",
            invalid_args_hint="Should not appear.",
        )
        message = tool_error_message(payload)
        assert "Pipe not found (ID: 42)" in message
        assert "Should not appear." not in message

    def test_fallthrough_legacy_for_unrelated_codes_when_opted_in(self):
        exc = _build_graphql_exc("INTERNAL_ERROR", "Something broke")
        payload = handle_tool_graphql_error(
            exc, "Failed", resource_kind="pipe", resource_id="42"
        )
        message = tool_error_message(payload)
        assert message == "Something broke"
        assert "search_pipes" not in message

    def test_permission_denied_enriched_when_resource_kind_passed(self):
        exc = _build_graphql_exc("PERMISSION_DENIED", "Permission denied")
        payload = handle_tool_graphql_error(
            exc, "Failed", resource_kind="pipe", resource_id="99999999"
        )
        message = tool_error_message(payload)
        assert "99999999" in message
        assert "may not exist" in message
        assert "may lack access" in message
        assert "search_pipes" in message
        assert payload["error"]["code"] == "PERMISSION_DENIED"

    def test_permission_denied_legacy_when_no_kind_passed(self):
        exc = _build_graphql_exc("PERMISSION_DENIED", "Permission denied")
        payload = handle_tool_graphql_error(exc, "Failed")
        message = tool_error_message(payload)
        assert message == "Permission denied"
        assert "may not exist" not in message

    def test_not_found_still_takes_precedence_over_ambiguous_access(self):
        # If both codes appeared (unlikely but possible), NOT_FOUND wins because
        # it is unambiguous.
        class _DualCodeExc(Exception):
            def __init__(self):
                super().__init__("Resource not found")
                self.errors = [
                    {"message": "Not found", "extensions": {"code": "NOT_FOUND"}},
                    {
                        "message": "Permission denied",
                        "extensions": {"code": "PERMISSION_DENIED"},
                    },
                ]

            def __str__(self):
                return "Resource not found"

        payload = handle_tool_graphql_error(
            _DualCodeExc(), "Failed", resource_kind="pipe", resource_id="42"
        )
        message = tool_error_message(payload)
        assert "Pipe not found (ID: 42)" in message
        assert "may not exist OR" not in message

    def test_debug_suffix_applies_to_enriched_message(self):
        exc = _build_graphql_exc("NOT_FOUND", "Pipe not found")
        payload = handle_tool_graphql_error(
            exc, "Failed", debug=True, resource_kind="pipe", resource_id="42"
        )
        message = tool_error_message(payload)
        assert "Pipe not found (ID: 42)" in message
        assert "codes=NOT_FOUND" in message

    @pytest.mark.parametrize(
        "kind,expected_label,expected_hint_substring",
        [
            ("pipe", "Pipe not found", "search_pipes"),
            ("card", "Card not found", "find_cards"),
            ("phase", "Phase not found", "get_pipe"),
            ("phase_field", "Phase field not found", "get_phase_fields"),
            ("table", "Table not found", "search_tables"),
            ("table_record", "Table record not found", "find_records"),
            ("field_condition", "Field condition not found", "get_field_conditions"),
            ("ai_agent", "Ai agent not found", "get_ai_agents"),
            ("ai_automation", "Ai automation not found", "get_ai_automations"),
            ("automation", "Automation not found", "get_automations"),
            ("label", "Label not found", "get_labels"),
            ("webhook", "Webhook not found", "get_webhooks"),
            ("organization", "Organization not found", "get_organization"),
        ],
    )
    def test_discovery_hint_matrix(self, kind, expected_label, expected_hint_substring):
        exc = _build_graphql_exc("NOT_FOUND", "Not found")
        result = enrich_not_found_error(exc, resource_kind=kind, resource_id="id_1")
        assert result is not None
        assert expected_label in result
        assert expected_hint_substring in result
