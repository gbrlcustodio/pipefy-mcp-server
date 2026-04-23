"""Tests for shared SSRF hostname resolution checks."""

import socket
from unittest.mock import patch

import pytest

from pipefy_mcp.services.pipefy.utils.url_ssrf import (
    assert_hostname_resolves_to_public_ips,
)


@pytest.mark.asyncio
async def test_assert_hostname_resolves_to_public_ips_rejects_loopback():
    with patch(
        "pipefy_mcp.services.pipefy.utils.url_ssrf.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0)),
        ],
    ):
        with pytest.raises(ValueError, match="private/internal"):
            await assert_hostname_resolves_to_public_ips("app.pipefy.com")


@pytest.mark.asyncio
async def test_assert_hostname_resolves_to_public_ips_rejects_aws_imds():
    with patch(
        "pipefy_mcp.services.pipefy.utils.url_ssrf.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0)),
        ],
    ):
        with pytest.raises(ValueError, match="private/internal"):
            await assert_hostname_resolves_to_public_ips("app.pipefy.com")
