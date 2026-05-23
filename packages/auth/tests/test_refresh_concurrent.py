"""Tests for ``ensure_fresh_session``'s cross-process refresh-lock shape.

Real cross-process semantics are kernel guarantees (covered for ``file_lock``
in ``test_locks.py``); these tests pin the *use* of the lock inside
``ensure_fresh_session`` — that it wraps the refresh+store window and that
the double-checked re-load lets the loser of a race skip its own POST.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pipefy_auth import refresh as refresh_module
from pipefy_auth.locks import RefreshLockTimeout
from pipefy_auth.storage import StoredSession

_ISSUER = "https://signin.example.com/realms/pipefy"
_CLIENT_ID = "pipefy-cli"


def _stored(*, obtained_at: int, expires_in: int = 30) -> StoredSession:
    return StoredSession(
        issuer=_ISSUER,
        client_id=_CLIENT_ID,
        access_token="OLD",
        refresh_token="OLD_R",
        token_type="Bearer",
        obtained_at=obtained_at,
        expires_in=expires_in,
        refresh_expires_in=None,
        scope=None,
        id_token=None,
    )


def _fresh(*, obtained_at: int) -> StoredSession:
    return StoredSession(
        issuer=_ISSUER,
        client_id=_CLIENT_ID,
        access_token="NEW",
        refresh_token="NEW_R",
        token_type="Bearer",
        obtained_at=obtained_at,
        expires_in=300,
        refresh_expires_in=None,
        scope=None,
        id_token=None,
    )


@pytest.mark.unit
def test_lock_brackets_refresh_and_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lock is entered before the refresh POST and exited after the keychain write."""
    events: list[str] = []

    @contextmanager
    def recording_lock(path: Path, *, timeout_s: float = 30.0) -> Iterator[None]:
        events.append("lock-enter")
        try:
            yield
        finally:
            events.append("lock-exit")

    monkeypatch.setattr(refresh_module, "file_lock", recording_lock)
    monkeypatch.setattr(
        refresh_module,
        "load_session",
        lambda issuer, client_id: _stored(obtained_at=int(time.time()) - 100),
    )

    refresh_called = MagicMock(
        return_value={"access_token": "NEW", "refresh_token": "NEW_R"}
    )
    store_called = MagicMock(return_value=_fresh(obtained_at=int(time.time())))
    monkeypatch.setattr(
        refresh_module,
        "refresh_access_token",
        lambda **kw: (events.append("refresh-post"), refresh_called(**kw))[1],
    )
    monkeypatch.setattr(
        refresh_module,
        "store_session",
        lambda **kw: (events.append("store"), store_called(**kw))[1],
    )

    result = refresh_module.ensure_fresh_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    assert result is not None
    assert events == ["lock-enter", "refresh-post", "store", "lock-exit"]


@pytest.mark.unit
def test_double_check_skips_refresh_when_session_fresh_under_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If another process refreshed while we waited, we observe their session and skip the POST."""
    stale = _stored(obtained_at=int(time.time()) - 100, expires_in=30)
    fresh = _fresh(obtained_at=int(time.time()))
    load_calls: list[StoredSession] = [stale, fresh]

    def fake_load(*, issuer: str, client_id: str) -> StoredSession:
        return load_calls.pop(0)

    monkeypatch.setattr(refresh_module, "load_session", fake_load)
    refresh_post = MagicMock()
    monkeypatch.setattr(refresh_module, "refresh_access_token", refresh_post)

    result = refresh_module.ensure_fresh_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    assert result is fresh
    refresh_post.assert_not_called()


@pytest.mark.unit
def test_lock_timeout_surfaces_as_refresh_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``RefreshLockTimeout`` is converted to ``RefreshError`` at the boundary."""
    monkeypatch.setattr(
        refresh_module,
        "load_session",
        lambda issuer, client_id: _stored(obtained_at=int(time.time()) - 100),
    )

    @contextmanager
    def timing_out_lock(path: Path, *, timeout_s: float = 30.0) -> Iterator[Any]:
        raise RefreshLockTimeout("simulated")
        yield  # pragma: no cover  (unreachable; here so this is a generator)

    monkeypatch.setattr(refresh_module, "file_lock", timing_out_lock)

    with pytest.raises(refresh_module.RefreshError) as exc_info:
        refresh_module.ensure_fresh_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    assert exc_info.value.error_code is None
    assert "refresh lock" in str(exc_info.value).lower()
