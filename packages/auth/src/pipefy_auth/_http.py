"""Shared httpx.Client context-manager helper for the OAuth flow modules."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Iterator

import httpx
from pipefy_infra.telemetry import auth_telemetry_headers


@contextmanager
def http_client(
    provided: httpx.Client | None, *, timeout: float
) -> Iterator[httpx.Client]:
    """Yield ``provided`` (without closing it) or a fresh ``httpx.Client``.

    The fresh client carries the auth telemetry headers so OAuth traffic to the
    IdP is attributable to a pipefy-auth version rather than anonymous httpx.
    """
    if provided is not None:
        with nullcontext(provided) as client:
            yield client
        return
    from pipefy_auth import __version__

    with httpx.Client(
        timeout=timeout, headers=auth_telemetry_headers(version=__version__)
    ) as client:
        yield client


__all__ = ["http_client"]
