"""Unit tests for pipe_config_tool_helpers error-message mappers.

Error message quality directly impacts agent recovery behavior: the actionable
text the tool returns tells the agent what to try next. These mappers run on
the error path only, so regressions are invisible in happy-path tests.
"""

from __future__ import annotations

import pytest

from pipefy_mcp.tools.pipe_config_tool_helpers import (
    field_condition_phase_field_id_looks_like_slug,
    map_delete_pipe_error_to_message,
)


class TestMapDeletePipeErrorToMessage:
    def test_resource_not_found_wins_over_other_codes(self):
        msg = map_delete_pipe_error_to_message(
            pipe_id="42",
            pipe_name="My Pipe",
            codes=["RESOURCE_NOT_FOUND", "PERMISSION_DENIED"],
        )
        assert "42" in msg
        assert "not found" in msg.lower()
        assert "access" in msg.lower()

    def test_permission_denied_message(self):
        msg = map_delete_pipe_error_to_message(
            pipe_id=7,
            pipe_name="P",
            codes=["PERMISSION_DENIED"],
        )
        assert "7" in msg
        assert "permission" in msg.lower()

    def test_record_not_destroyed_message_includes_name(self):
        msg = map_delete_pipe_error_to_message(
            pipe_id="99",
            pipe_name="Launch Pipe",
            codes=["RECORD_NOT_DESTROYED"],
        )
        assert "Launch Pipe" in msg
        assert "99" in msg
        assert "Try again" in msg or "support" in msg.lower()

    def test_unknown_code_falls_back_to_code_list(self):
        msg = map_delete_pipe_error_to_message(
            pipe_id="1",
            pipe_name="Name",
            codes=["UNKNOWN_CODE_A", "UNKNOWN_CODE_B"],
        )
        assert "Name" in msg
        assert "UNKNOWN_CODE_A, UNKNOWN_CODE_B" in msg

    def test_empty_codes_falls_back_to_generic_message(self):
        msg = map_delete_pipe_error_to_message(
            pipe_id="1",
            pipe_name="Name",
            codes=[],
        )
        assert "Name" in msg
        assert "1" in msg
        assert "Codes:" not in msg  # no code list rendered


class TestFieldConditionPhaseFieldIdLooksLikeSlug:
    """Safeguard for agents that pass a slug (alpha characters) as phaseFieldId.

    The heuristic must accept numeric IDs, UUIDs, and integers as valid, and
    only flag true slugs so the tool can produce a clear ``internal_id`` hint
    instead of a generic GraphQL error.
    """

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("308821043", False),
            ("99", False),
            ("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11", False),
            ("my_custom_field", True),
            ("prioridade", True),
            ("", False),
            ("___", False),
            ("  ", False),
        ],
    )
    def test_heuristic(self, value, expected):
        assert field_condition_phase_field_id_looks_like_slug(value) is expected

    def test_rejects_integers(self):
        assert field_condition_phase_field_id_looks_like_slug(308821043) is False

    def test_rejects_non_string_non_int(self):
        assert field_condition_phase_field_id_looks_like_slug(None) is False
        assert field_condition_phase_field_id_looks_like_slug([]) is False
