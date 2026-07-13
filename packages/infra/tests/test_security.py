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
        with pytest.raises(ValueError, match="blocked address"):
            await security.assert_hostname_resolves_to_public_ips("app.pipefy.com")


@pytest.mark.unit
def test_validate_https_url_rejects_http():
    with pytest.raises(ValueError, match="must use HTTPS"):
        security.validate_https_url(
            "http://app.pipefy.com/g", "graphql_url", allow_insecure=False
        )


@pytest.mark.unit
def test_validate_https_url_rejects_non_http_scheme_with_scheme_in_message():
    # The error mentions the offending scheme so operators can spot the
    # typo (``file://``, ``ftp://``, ``data:...``) without re-reading the
    # input value.
    with pytest.raises(ValueError, match="got file://"):
        security.validate_https_url("file:///etc/passwd", "url", allow_insecure=False)


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
        with pytest.raises(ValueError, match="blocked address"):
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
        with pytest.raises(ValueError, match="blocked address"):
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
    with pytest.raises(ValueError, match="blocked range"):
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


@pytest.mark.unit
@pytest.mark.parametrize(
    "blocked_ip",
    [
        "224.0.0.1",  # multicast
        "239.255.255.250",  # multicast (SSDP)
        "240.0.0.1",  # reserved (class E)
        "0.0.0.0",  # unspecified
    ],
)
def test_assert_hostname_is_not_internal_rejects_multicast_reserved_unspecified(
    blocked_ip: str,
) -> None:
    # ``_is_blocked_ip`` widens beyond the legacy private/loopback/link-local
    # set by ORing in is_multicast / is_reserved / is_unspecified. These
    # tests pin the broadened coverage so a future narrowing reverts the
    # gate visibly instead of silently.
    with pytest.raises(ValueError, match="blocked range"):
        security.assert_hostname_is_not_internal(blocked_ip, context="url")


@pytest.mark.unit
@pytest.mark.parametrize(
    "bracketed",
    ["[::1]", "[fe80::1]", "[::ffff:127.0.0.1]"],
)
def test_assert_hostname_is_not_internal_rejects_bracketed_ipv6(
    bracketed: str,
) -> None:
    # Direct callers that don't go through ``urlparse`` (which strips
    # brackets) still hit the IP gate via the defensive bracket-strip.
    with pytest.raises(ValueError, match="blocked range"):
        security.assert_hostname_is_not_internal(bracketed, context="url")


@pytest.mark.asyncio
async def test_assert_hostname_resolves_to_public_ips_wraps_unicode_error():
    # ``socket.getaddrinfo`` raises ``UnicodeError`` (not ``gaierror``) for
    # IDN encoding failures, e.g. a >63-char label. The gate normalizes it
    # to the same ``ValueError`` contract callers expect.
    with patch(
        "pipefy_infra.security.socket.getaddrinfo",
        side_effect=UnicodeError("encoding with 'idna' codec failed"),
    ):
        with pytest.raises(ValueError, match="Could not resolve hostname"):
            await security.assert_hostname_resolves_to_public_ips("a" * 64 + ".example")


@pytest.mark.unit
@pytest.mark.parametrize(
    "good_url",
    [
        "https://idp.example.com/realms/pipefy",
        "https://idp.example.com",
        "https://idp.example.com/",
    ],
)
def test_assert_url_has_no_query_or_fragment_accepts_paths(good_url: str) -> None:
    security.assert_url_has_no_query_or_fragment(good_url, field_label="auth_url")


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_url",
    [
        "https://idp.example.com/realms/pipefy?token=secret",
        "https://idp.example.com#frag",
        "https://idp.example.com/realms?a=b",
    ],
)
def test_assert_url_has_no_query_or_fragment_rejects_query_or_fragment(
    bad_url: str,
) -> None:
    with pytest.raises(ValueError, match="query string or fragment"):
        security.assert_url_has_no_query_or_fragment(bad_url, field_label="auth_url")


@pytest.mark.asyncio
async def test_validate_and_assert_public_url_returns_hostname():
    with patch(
        "pipefy_infra.security.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
        ],
    ):
        hostname = await security.validate_and_assert_public_url(
            "https://example.com/file.pdf", field_label="url"
        )
        assert hostname == "example.com"


@pytest.mark.asyncio
async def test_validate_and_assert_public_url_rejects_internal_via_sync_gate():
    # Sync gate runs first; literal-IP rejection fires before any DNS call.
    with pytest.raises(ValueError, match="blocked range"):
        await security.validate_and_assert_public_url(
            "https://10.0.0.1/secret", field_label="url"
        )


@pytest.mark.asyncio
async def test_validate_and_assert_public_url_allow_insecure_skips_literal_ip():
    # ``allow_insecure=True`` skips the sync literal-IP gate; the async DNS
    # gate is the only remaining defense. With a public-IP-mocked resolver,
    # the call succeeds even though the URL literal looks internal-ish.
    with patch(
        "pipefy_infra.security.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
        ],
    ):
        hostname = await security.validate_and_assert_public_url(
            "http://127.0.0.1/local-only",
            field_label="url",
            allow_insecure=True,
        )
        assert hostname == "127.0.0.1"


@pytest.mark.unit
@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "127.0.0.2", "localhost", "LOCALHOST", "::1", "[::1]", " ::1 "],
)
def test_is_loopback_host_accepts_loopback(host: str) -> None:
    assert security.is_loopback_host(host) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "203.0.113.5", "example.com", "", "   "],
)
def test_is_loopback_host_rejects_non_loopback(host: str) -> None:
    assert security.is_loopback_host(host) is False
