"""Tests for shared SSRF hostname resolution checks."""

import socket
from unittest.mock import patch

import pytest

from pipefy_mcp.services.pipefy.utils.url_ssrf import (
    assert_hostname_is_not_internal,
    assert_hostname_resolves_to_public_ips,
    validate_https_service_endpoint_url,
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


@pytest.mark.unit
def test_validate_https_service_endpoint_url_rejects_http():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_https_service_endpoint_url(
            "http://app.pipefy.com/g", "graphql_url", allow_insecure=False
        )


@pytest.mark.unit
def test_validate_https_allow_insecure_accepts_http_localhost():
    validate_https_service_endpoint_url(
        "http://127.0.0.1/g", "graphql_url", allow_insecure=True
    )


@pytest.mark.unit
def test_assert_hostname_is_not_internal_rejects_localhost_name():
    with pytest.raises(ValueError, match="localhost"):
        assert_hostname_is_not_internal("localhost", context="url")


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
