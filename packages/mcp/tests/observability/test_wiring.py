"""Tests for hosted observability wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP
from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings

from pipefy_mcp.observability.request_log_middleware import RequestLogMiddleware
from pipefy_mcp.observability.wiring import wire_hosted_observability
from pipefy_mcp.settings import McpSettings, Settings

_SETTINGS = Settings(
    pipefy=PipefySettings(base_url="https://api.pipefy.com"),
    auth=AuthSettings(),
    mcp=McpSettings(transport="http"),
)


@pytest.mark.unit
def test_wire_hosted_observability_calls_streamable_http_app_once() -> None:
    app = FastMCP("test")
    starlette_app = MagicMock()

    with patch.object(app, "streamable_http_app", return_value=starlette_app) as mock_app:
        result = wire_hosted_observability(app, _SETTINGS)

    mock_app.assert_called_once_with()
    assert result is starlette_app


@pytest.mark.unit
def test_wire_hosted_observability_adds_request_log_middleware() -> None:
    app = FastMCP("test")
    starlette_app = MagicMock()

    with patch.object(app, "streamable_http_app", return_value=starlette_app):
        wire_hosted_observability(app, _SETTINGS)

    starlette_app.add_middleware.assert_called_once_with(RequestLogMiddleware)
