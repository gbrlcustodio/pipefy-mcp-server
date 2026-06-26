"""Tests for the shared auth httpx client helper (telemetry headers)."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from pipefy_auth import __version__
from pipefy_auth._http import http_client


@pytest.mark.unit
def test_fresh_client_sends_auth_telemetry_headers():
    """A fresh auth client tags OAuth requests with the pipefy-auth telemetry headers.

    Runs the real httpx client, swapping only the network transport for an
    ``httpx.MockTransport`` that captures the sent headers.
    """
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={})

    real_client = httpx.Client

    def client_factory(**kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    with patch("httpx.Client", side_effect=client_factory):
        with http_client(None, timeout=5.0) as client:
            client.post("https://signin.pipefy.com/realms/pipefy/token", data={})

    headers = captured["headers"]
    assert headers["user-agent"] == f"pipefy-auth/{__version__}"
    assert headers["x-client-name"] == "auth"
    assert headers["x-client-version"] == __version__


@pytest.mark.unit
def test_provided_client_is_used_untouched():
    """A caller-provided client is yielded as-is (no UA override, left open)."""
    provided = httpx.Client(headers={"User-Agent": "caller/1.0"})
    with http_client(provided, timeout=5.0) as client:
        assert client is provided
        assert client.headers["user-agent"] == "caller/1.0"
    assert not provided.is_closed
    provided.close()
