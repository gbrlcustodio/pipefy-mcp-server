"""Unit tests for report_tool_helpers — both flag states (REQ-3, ADR-0001)."""

import pytest

from pipefy_mcp.tools.report_tool_helpers import (
    build_report_mutation_success_payload,
    build_report_read_success_payload,
)


@pytest.mark.unit
def test_build_report_read_success_payload_flag_on(unified_envelope):
    raw = {"pipeReports": {"edges": [{"node": {"id": "r1"}}], "pageInfo": {}}}
    out = build_report_read_success_payload(raw, message="Pipe reports retrieved.")
    # ADR-0001: verbatim wrap — 'pipeReports' key is preserved inside data.
    assert out == {
        "success": True,
        "data": raw,
        "message": "Pipe reports retrieved.",
    }
    assert "pipeReports" in out["data"]


@pytest.mark.unit
def test_build_report_read_success_payload_flag_off(legacy_envelope):
    raw = {"pipeReports": {"edges": [], "pageInfo": {}}}
    out = build_report_read_success_payload(raw, message="Pipe reports retrieved.")
    # Legacy shape — byte-identical to pre-PR output.
    assert out == {
        "success": True,
        "message": "Pipe reports retrieved.",
        "data": raw,
    }


@pytest.mark.unit
def test_build_report_read_success_payload_parametrized(envelope_flag):
    raw = {"pipeReport": {"id": "42", "name": "Alpha"}}
    out = build_report_read_success_payload(raw, message="ok")
    # Both states — 'data' always holds the verbatim GraphQL subtree.
    assert out["success"] is True
    assert out["data"] == raw
    assert out["message"] == "ok"


@pytest.mark.unit
def test_build_report_mutation_success_payload_flag_on(unified_envelope):
    raw = {"createPipeReport": {"pipeReport": {"id": "9"}}}
    out = build_report_mutation_success_payload(message="Created.", data=raw)
    assert out == {"success": True, "data": raw, "message": "Created."}
    assert "result" not in out


@pytest.mark.unit
def test_build_report_mutation_success_payload_flag_off(legacy_envelope):
    raw = {"createPipeReport": {"pipeReport": {"id": "9"}}}
    out = build_report_mutation_success_payload(message="Created.", data=raw)
    # Legacy shape — raw payload sits under 'result'.
    assert out == {"success": True, "message": "Created.", "result": raw}
    assert "data" not in out
