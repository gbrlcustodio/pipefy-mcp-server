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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "v4_mapped_v6",
    [
        "::ffff:127.0.0.1",  # loopback
        "::ffff:10.0.0.1",  # RFC1918
        "::ffff:169.254.169.254",  # AWS IMDS (link-local)
        "::ffff:192.168.1.1",  # RFC1918
        "::ffff:172.16.0.1",  # RFC1918
    ],
)
async def test_assert_hostname_resolves_to_public_ips_rejects_ipv4_mapped_ipv6(
    v4_mapped_v6: str,
) -> None:
    # Plain network-membership against a v4 network misses v4-mapped v6
    # literals (different address family). The stdlib ``is_*`` properties
    # cross the family boundary via the embedded v4 portion; this test pins
    # that the gate uses those.
    with patch(
        "pipefy_infra.security.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET6, socket.SOCK_STREAM, 0, "", (v4_mapped_v6, 0, 0, 0)),
        ],
    ):
        with pytest.raises(ValueError, match="private/internal"):
            await security.assert_hostname_resolves_to_public_ips("evil.example.com")


@pytest.mark.unit
@pytest.mark.parametrize(
    "v4_mapped_v6",
    [
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "::ffff:169.254.169.254",
    ],
)
def test_assert_hostname_is_not_internal_rejects_ipv4_mapped_ipv6(
    v4_mapped_v6: str,
) -> None:
    with pytest.raises(ValueError, match="private, loopback, or link-local"):
        security.assert_hostname_is_not_internal(v4_mapped_v6, context="url")


@pytest.mark.asyncio
async def test_assert_hostname_resolves_to_public_ips_raises_on_empty_addr_info():
    with patch("pipefy_infra.security.socket.getaddrinfo", return_value=[]):
        with pytest.raises(ValueError, match="no addresses returned"):
            await security.assert_hostname_resolves_to_public_ips("app.pipefy.com")


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_url",
    [
        "https://app.pipefy.com//",
        "https://app.pipefy.com///",
        "https://app.pipefy.com/path",
        "https://app.pipefy.com?q=1",
        "https://app.pipefy.com#frag",
    ],
)
def test_assert_url_is_host_root_rejects_non_root(bad_url: str) -> None:
    with pytest.raises(ValueError, match="host root"):
        security.assert_url_is_host_root(bad_url, field_label="base_url")


@pytest.mark.unit
@pytest.mark.parametrize(
    "good_url",
    [
        "https://app.pipefy.com",
        "https://app.pipefy.com/",
        "http://localhost:8080",
    ],
)
def test_assert_url_is_host_root_accepts_root(good_url: str) -> None:
    security.assert_url_is_host_root(good_url, field_label="base_url")
