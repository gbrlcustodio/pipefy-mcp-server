"""Tests for the SSRF defenses (shape gate, sync host gate, async DNS gate)."""

import re
import socket
from unittest.mock import patch

import pytest

from pipefy_infra import security


@pytest.mark.unit
@pytest.mark.parametrize(
    "url",
    [
        "https://app.pipefy.com",
        "http://app.pipefy.com",
        "HTTPS://app.pipefy.com",
        "Http://localhost:8080/path",
        "https://app.pipefy.com/graphql?x=1",
    ],
)
def test_url_shape_pattern_accepts_https_and_http(url: str) -> None:
    assert re.match(security.URL_SHAPE_PATTERN, url) is not None


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "ftp://app.pipefy.com",
        "app.pipefy.com",
        "https://",
        "https://has whitespace",
    ],
)
def test_url_shape_pattern_rejects_non_http_or_empty(value: str) -> None:
    assert re.match(security.URL_SHAPE_PATTERN, value) is None


@pytest.mark.asyncio
async def test_assert_hostname_resolves_to_public_ips_rejects_loopback():
    with patch(
        "pipefy_infra.security.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0)),
        ],
    ):
        with pytest.raises(ValueError, match="private/internal"):
            await security.assert_hostname_resolves_to_public_ips("app.pipefy.com")


@pytest.mark.unit
def test_validate_https_url_rejects_http():
    with pytest.raises(ValueError, match="HTTPS"):
        security.validate_https_url(
            "http://app.pipefy.com/g", "graphql_url", allow_insecure=False
        )


@pytest.mark.unit
def test_validate_https_allow_insecure_accepts_http_localhost():
    security.validate_https_url(
        "http://127.0.0.1/g", "graphql_url", allow_insecure=True
    )


@pytest.mark.unit
def test_assert_hostname_is_not_internal_rejects_localhost_name():
    with pytest.raises(ValueError, match="localhost"):
        security.assert_hostname_is_not_internal("localhost", context="url")


@pytest.mark.asyncio
async def test_assert_hostname_resolves_to_public_ips_rejects_aws_imds():
    with patch(
        "pipefy_infra.security.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0)),
        ],
    ):
        with pytest.raises(ValueError, match="private/internal"):
            await security.assert_hostname_resolves_to_public_ips("app.pipefy.com")
