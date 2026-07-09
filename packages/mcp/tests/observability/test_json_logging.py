"""Tests for structured JSON log event builders."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

import pytest

from pipefy_mcp.observability.json_logging import (
    HTTP_REQUEST_EVENT_KEYS,
    OBSERVABILITY_LOGGER_NAME,
    TOOL_CALL_EVENT_KEYS,
    ToolCallOutcome,
    build_http_request_event,
    build_tool_call_event,
    configure_observability_logging,
    emit_structured_event,
    normalize_log_level,
    reset_observability_logging,
)

_FIXED_TIMESTAMP = datetime(2026, 7, 7, 22, 15, 30, tzinfo=UTC)


class TestBuildHttpRequestEvent:
    def test_has_expected_fields(self):
        event = build_http_request_event(
            method="POST",
            path="/mcp",
            status=200,
            duration_ms=42,
            client_ip="127.0.0.1",
            session_id="sess-abc",
            request_id="req-123",
            sub="user-subject",
            client_id="client-azp",
            timestamp=_FIXED_TIMESTAMP,
        )

        assert set(event.keys()) == HTTP_REQUEST_EVENT_KEYS
        assert event == {
            "event": "http_request",
            "timestamp": "2026-07-07T22:15:30+00:00",
            "method": "POST",
            "path": "/mcp",
            "status": 200,
            "duration_ms": 42,
            "client_ip": "127.0.0.1",
            "session_id": "sess-abc",
            "request_id": "req-123",
            "sub": "user-subject",
            "client_id": "client-azp",
        }

    def test_null_identity_fields_when_absent(self):
        event = build_http_request_event(
            method="GET",
            path="/health",
            status=None,
            duration_ms=1,
            client_ip=None,
            session_id=None,
            request_id="req-null",
            sub=None,
            client_id=None,
            timestamp=_FIXED_TIMESTAMP,
        )

        assert event["sub"] is None
        assert event["client_id"] is None
        assert event["status"] is None

    def test_output_is_json_serializable_one_line(self):
        event = build_http_request_event(
            method="POST",
            path="/mcp",
            status=200,
            duration_ms=10,
            client_ip="127.0.0.1",
            session_id="s",
            request_id="r",
            sub=None,
            client_id=None,
            timestamp=_FIXED_TIMESTAMP,
        )

        line = json.dumps(event, separators=(",", ":"))
        assert "\n" not in line
        assert json.loads(line) == event


class TestBuildToolCallEvent:
    def test_has_expected_fields(self):
        event = build_tool_call_event(
            tool="get_card",
            outcome="ok",
            duration_ms=15,
            arg_keys=["card_id"],
            request_id="req-456",
            timestamp=_FIXED_TIMESTAMP,
        )

        assert set(event.keys()) == TOOL_CALL_EVENT_KEYS
        assert event == {
            "event": "tool_call",
            "timestamp": "2026-07-07T22:15:30+00:00",
            "tool": "get_card",
            "outcome": "ok",
            "duration_ms": 15,
            "arg_keys": ["card_id"],
            "request_id": "req-456",
        }

    @pytest.mark.parametrize("outcome", ["ok", "error"])
    def test_outcome_is_ok_or_error(self, outcome: ToolCallOutcome):
        event = build_tool_call_event(
            tool="find_cards",
            outcome=outcome,
            duration_ms=3,
            arg_keys=["pipe_id", "title"],
            request_id="req-outcome",
            timestamp=_FIXED_TIMESTAMP,
        )

        assert event["outcome"] == outcome

    def test_request_id_null_when_uncorrelated(self):
        event = build_tool_call_event(
            tool="get_pipe",
            outcome="ok",
            duration_ms=2,
            arg_keys=[],
            request_id=None,
            timestamp=_FIXED_TIMESTAMP,
        )

        assert event["request_id"] is None


class TestObservabilityLoggingEmitter:
    @pytest.fixture(autouse=True)
    def _isolated_logger(self):
        reset_observability_logging()
        yield
        reset_observability_logging()

    def test_emits_valid_json_one_liner_on_stdout(self, capsys):
        configure_observability_logging(log_level="INFO")
        event = build_http_request_event(
            method="POST",
            path="/mcp",
            status=200,
            duration_ms=10,
            client_ip="127.0.0.1",
            session_id=None,
            request_id="req-emit",
            sub=None,
            client_id=None,
            timestamp=_FIXED_TIMESTAMP,
        )

        emit_structured_event(event)

        line = capsys.readouterr().out.strip()
        assert "\n" not in line
        assert json.loads(line) == event

    def test_warning_level_suppresses_info_events(self, capsys):
        configure_observability_logging(log_level="WARNING")
        emit_structured_event(
            build_tool_call_event(
                tool="get_card",
                outcome="ok",
                duration_ms=1,
                arg_keys=["card_id"],
                request_id="req-muted",
                timestamp=_FIXED_TIMESTAMP,
            )
        )

        assert capsys.readouterr().out == ""

    def test_does_not_propagate_to_root_logger(self):
        root = logging.getLogger()
        captured: list[logging.LogRecord] = []

        class _CapturingHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        root_handler = _CapturingHandler()
        root.addHandler(root_handler)
        root.setLevel(logging.DEBUG)
        try:
            configure_observability_logging(log_level="INFO")
            emit_structured_event(
                build_http_request_event(
                    method="GET",
                    path="/mcp",
                    status=200,
                    duration_ms=1,
                    client_ip=None,
                    session_id=None,
                    request_id="req-root",
                    sub=None,
                    client_id=None,
                    timestamp=_FIXED_TIMESTAMP,
                )
            )
            assert captured == []
        finally:
            root.removeHandler(root_handler)

    def test_handler_targets_stdout_explicitly(self):
        configure_observability_logging(log_level="INFO")
        logger = logging.getLogger(OBSERVABILITY_LOGGER_NAME)
        assert len(logger.handlers) == 1
        assert logger.handlers[0].stream is sys.stdout
        assert logger.propagate is False

    def test_configure_twice_keeps_one_handler_and_one_line(self, capsys):
        configure_observability_logging(log_level="INFO")
        configure_observability_logging(log_level="INFO")

        emit_structured_event(
            build_tool_call_event(
                tool="get_card",
                outcome="ok",
                duration_ms=1,
                arg_keys=[],
                request_id="req-once",
                timestamp=_FIXED_TIMESTAMP,
            )
        )

        logger = logging.getLogger(OBSERVABILITY_LOGGER_NAME)
        assert len(logger.handlers) == 1
        assert len(capsys.readouterr().out.strip().splitlines()) == 1

    def test_normalize_log_level_rejects_unknown_name(self):
        with pytest.raises(ValueError, match="invalid log level"):
            normalize_log_level("verbose")

    def test_normalize_log_level_rejects_non_level_logging_attribute(self):
        # getattr(logging, ...) resolves module attributes that are not levels;
        # anything that does not map to an int level must be rejected.
        with pytest.raises(ValueError, match="invalid log level"):
            normalize_log_level("BASIC_FORMAT")
