"""Shared httpx.Client context-manager helper for the OAuth flow modules."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Iterator

import httpx


@contextmanager
def http_client(
    provided: httpx.Client | None, *, timeout: float
) -> Iterator[httpx.Client]:
    """Yield ``provided`` (without closing it) or a fresh ``httpx.Client``."""
    if provided is not None:
        with nullcontext(provided) as client:
            yield client
        return
    with httpx.Client(timeout=timeout) as client:
        yield client


__all__ = ["http_client"]
