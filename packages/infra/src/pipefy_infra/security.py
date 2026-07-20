"""SSRF defenses on URLs destined for outbound HTTP.

Surface:

* :data:`URL_SHAPE_PATTERN`: regex matching ``http(s)://<non-whitespace>``.
  Cheap shape check; the deeper scheme/hostname/IP checks live in
  :func:`validate_https_url`.
* :func:`validate_https_url`: synchronous scheme + literal-IP gate.
  Enforces HTTPS and rejects literal IPs in
  private/loopback/link-local/multicast/reserved/unspecified ranges.
  ``allow_insecure=True`` also accepts ``http://`` and skips the
  literal-IP check (callers must follow up with the DNS gate).
* :func:`assert_hostname_is_not_internal`: building block of the above;
  exposed for callers that already have a parsed hostname.
* :func:`is_loopback_host`: predicate reporting whether a bind host keeps
  a server reachable only from the local machine (``localhost`` or a
  literal IP in ``127.0.0.0/8`` or ``::1``).
* :func:`assert_hostname_resolves_to_public_ips`: asynchronous DNS gate.
  Resolves the hostname and rejects when any resolved IP is in a blocked
  range. Counter to DNS-rebinding attacks that point a public name at an
  internal IP after validation.
* :func:`validate_and_assert_public_url`: composite of the sync and DNS
  gates; returns the validated hostname.
* :func:`assert_url_is_host_root`: shape helper, rejects any path beyond
  ``/`` plus any query/fragment. For URLs that downstream concatenates
  path suffixes onto.
* :func:`assert_url_has_no_query_or_fragment`: shape helper, allows a
  path but rejects query/fragment. For URLs that may carry a path but
  whose downstream still concatenates additional path segments.

Import the module (``from pipefy_infra import security``) and call
through it (``security.validate_https_url(...)``) so call sites are
greppable for security review.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

# Regex for the URL shape ``http(s)://<non-whitespace>``. Scheme is
# case-insensitive (RFC 3986 §3.1) so ``HTTPS://...`` matches.
URL_SHAPE_PATTERN = r"^(?i:https?)://\S+$"

# Human-readable enumeration of the address categories ``_is_blocked_ip``
# rejects. Substituted into error messages so the reason is visible
# without consulting the source.
_BLOCKED_RANGES_LABEL = (
    "private, loopback, link-local, multicast, reserved, or unspecified"
)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # Listing the stdlib ``is_*`` properties explicitly (rather than
    # ``not ip.is_global``) keeps the blocked set intent-explicit AND
    # transparently covers IPv4-mapped IPv6 (e.g. ``::ffff:127.0.0.1``):
    # the properties cross the family boundary via the embedded v4 portion.
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_hostname_is_not_internal(hostname: str, *, context: str) -> None:
    """Reject localhost and literal IPs in blocked ranges.

    Blocked ranges: private, loopback, link-local, multicast, reserved,
    unspecified. Domain names are not DNS-resolved here (use
    :func:`assert_hostname_resolves_to_public_ips` before fetching).

    Bracketed IPv6 literals (``[::1]``) are tolerated for callers that
    pass a raw URL host slot rather than ``urlparse(...).hostname``.

    Raises:
        ValueError: When the host is disallowed.
    """
    host = (hostname or "").strip().lower()
    if not host:
        raise ValueError(f"{context}: URL must include a hostname.")
    if host == "localhost":
        raise ValueError(f"{context}: localhost hostnames are not allowed.")

    # Strip IPv6 brackets so a caller passing the raw URL netloc (rather
    # than ``urlparse(...).hostname``, which auto-strips them) still hits
    # the IP gate. Without this, ``ipaddress.ip_address('[::1]')`` raises
    # ValueError and the literal would slip past as "not an IP".
    candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host

    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        return

    if _is_blocked_ip(ip):
        raise ValueError(
            f"{context}: {hostname!r} is in a blocked range "
            f"({_BLOCKED_RANGES_LABEL}) and is not allowed."
        )


def is_loopback_host(host: str) -> bool:
    """Report whether ``host`` binds a server to the local machine only.

    Loopback means ``localhost`` or a literal IP in ``127.0.0.0/8`` or ``::1``.
    ``0.0.0.0`` (and ``::``) is unspecified, not loopback, so it is reported as
    non-loopback. A hostname that is not a literal IP (anything other than
    ``localhost``) is reported as non-loopback: it is not resolved here, and
    treating an unresolved name as reachable is the safe default for a
    bind-safety gate.

    Bracketed IPv6 literals (``[::1]``) are tolerated for callers passing a raw
    URL host slot rather than ``urlparse(...).hostname``.
    """
    candidate = (host or "").strip().lower()
    if candidate == "localhost":
        return True
    candidate = (
        candidate[1:-1]
        if candidate.startswith("[") and candidate.endswith("]")
        else candidate
    )
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def validate_https_url(
    url: str,
    field_label: str,
    *,
    allow_insecure: bool = False,
) -> None:
    """Validate a URL destined for outbound HTTP.

    Default mode enforces HTTPS and rejects literal IPs in blocked ranges
    (private, loopback, link-local, multicast, reserved, unspecified).

    When ``allow_insecure=True``:
        * ``http://`` is also accepted.
        * The literal-IP gate is SKIPPED so ``http://127.0.0.1`` is
          accepted. Callers that need to block internal IPs in this mode
          must follow up with
          :func:`assert_hostname_resolves_to_public_ips` (or use
          :func:`validate_and_assert_public_url` to bundle both gates).

    Raises:
        ValueError: When the URL is missing parts or violates policy.
    """
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        raise ValueError(f"{field_label}: URL must include a scheme.")

    # Scheme validation runs before the hostname check so an unsupported
    # scheme (file://, ftp://, ...) raises a clear "wrong scheme" error
    # rather than the misleading "missing hostname" one that urlparse
    # would otherwise trigger for URLs whose netloc parses as empty.
    scheme = parsed.scheme.lower()
    if allow_insecure:
        if scheme not in ("http", "https"):
            raise ValueError(f"{field_label}: must use http or https.")
    elif scheme != "https":
        raise ValueError(f"{field_label}: must use HTTPS (got {scheme}://).")

    if not parsed.hostname:
        raise ValueError(f"{field_label}: URL must include a hostname.")

    if not allow_insecure:
        assert_hostname_is_not_internal(parsed.hostname, context=field_label)


def assert_url_is_host_root(url: str, *, field_label: str) -> None:
    """Assert ``url`` is a host root: empty path or ``/``, no query, no fragment.

    Repeated-slash paths (``//``, ``///``) are rejected: they pass a naive
    ``path.strip('/')`` check but lead downstream f-string concatenation to
    emit double-slash URLs that route inconsistently. ``parsed.path`` must
    be exactly ``''`` or ``'/'``.

    Raises:
        ValueError: When the URL has a non-root path, query, or fragment.
    """
    parsed = urlparse(url)
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError(
            f"{field_label} must be a host root with no path, query, or fragment "
            f"(got {url!r})."
        )


def assert_url_has_no_query_or_fragment(url: str, *, field_label: str) -> None:
    """Assert ``url`` has no query string or fragment. Path is allowed.

    Looser than :func:`assert_url_is_host_root`: a path is permitted, so
    use this for URLs that may carry a path but onto which downstream
    code still concatenates further segments (a stray query or fragment
    would land between the original URL and the suffix).

    Raises:
        ValueError: When the URL has a query string or fragment.
    """
    parsed = urlparse(url)
    if parsed.query or parsed.fragment:
        raise ValueError(
            f"{field_label} must not carry a query string or fragment (got {url!r})."
        )


async def assert_hostname_resolves_to_public_ips(hostname: str) -> None:
    """Resolve ``hostname`` and ensure no address is in a blocked range.

    DNS resolution runs in a thread pool to avoid blocking the event loop.
    ``socket.getaddrinfo`` may raise either ``socket.gaierror`` (resolver
    failure) or ``UnicodeError`` (IDN encoding failure, e.g. a >63-char
    label); both surface as a uniform ``ValueError``.

    Raises:
        ValueError: When resolution fails, returns no addresses, or any
            resolved IP is in a blocked range (private/loopback/link-local/
            multicast/reserved/unspecified).
    """
    if not hostname:
        raise ValueError("URL has no hostname.")

    try:
        loop = asyncio.get_running_loop()
        addr_info = await loop.run_in_executor(
            None, socket.getaddrinfo, hostname, None, 0, socket.SOCK_STREAM
        )
    except (socket.gaierror, UnicodeError) as exc:
        raise ValueError(f"Could not resolve hostname {hostname!r}: {exc}") from exc

    if not addr_info:
        raise ValueError(
            f"Could not resolve hostname {hostname!r}: no addresses returned."
        )

    for _family, _type, _proto, _canonname, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        if _is_blocked_ip(ip):
            raise ValueError(
                f"Host {hostname!r} resolves to a blocked address ({ip}): "
                f"in {_BLOCKED_RANGES_LABEL} range. Request blocked."
            )


async def validate_and_assert_public_url(
    url: str,
    *,
    field_label: str,
    allow_insecure: bool = False,
) -> str:
    """Run the sync gate + DNS gate together; return the validated hostname.

    Equivalent to ``validate_https_url`` followed by
    ``assert_hostname_resolves_to_public_ips`` on the parsed hostname.

    Raises:
        ValueError: Same conditions as the individual gates.
    """
    validate_https_url(url, field_label, allow_insecure=allow_insecure)
    hostname = urlparse(url.strip()).hostname or ""
    await assert_hostname_resolves_to_public_ips(hostname)
    return hostname


__all__ = [
    "URL_SHAPE_PATTERN",
    "assert_hostname_is_not_internal",
    "assert_hostname_resolves_to_public_ips",
    "assert_url_has_no_query_or_fragment",
    "assert_url_is_host_root",
    "validate_and_assert_public_url",
    "validate_https_url",
]
