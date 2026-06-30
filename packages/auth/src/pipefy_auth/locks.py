"""Cross-process serialization for the refresh-token grant.

POSIX uses ``fcntl.flock(LOCK_EX | LOCK_NB)`` polled until acquired (kernel-
managed, FD-bound, released on process exit including SIGKILL). Windows uses
``msvcrt.locking(LK_NBLCK)`` with the same polled shape. Lock window is
~200-500ms (one POST + one keychain write); 30s is the deadlock backstop.

The advisory `fcntl.flock` guarantee is cross-process on local filesystems
but historically unreliable over NFS; the lock file lives under
:func:`pipefy_infra.paths.config_dir` (typically ``~/.config/pipefy``) which is
typically local. NFS-home users silently lose the cross-process
serialisation but the refresh still works.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pipefy_infra.paths import config_dir

_POLL_INTERVAL_S = 0.05


class RefreshLockTimeout(RuntimeError):
    """Could not acquire the cross-process refresh lock within timeout."""


def refresh_lock_path() -> Path:
    """Filesystem path used to coordinate concurrent refreshes (pure).

    One global lock per host, not per ``(issuer, client_id)`` — multi-account
    isn't a current goal. Sits next to ``config.toml`` under
    :func:`pipefy_infra.paths.config_dir`.
    """
    return config_dir() / "refresh.lock"


@contextmanager
def file_lock(path: Path, *, timeout_s: float = 30.0) -> Iterator[None]:
    """Acquire an exclusive cross-process lock backed by ``path``.

    Open with ``O_CREAT | O_RDWR`` (never ``O_TRUNC`` — concurrent acquirers
    would race on truncation). The lock file persists across runs; that is
    fine: an existing inode with no active kernel lock is the normal state.

    Raises:
        RefreshLockTimeout: When the lock cannot be acquired within ``timeout_s``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if sys.platform == "win32":
            _acquire_windows(fd, timeout_s)
        else:
            _acquire_posix(fd, timeout_s)
        try:
            yield
        finally:
            _release(fd)
    finally:
        os.close(fd)


def _acquire_posix(fd: int, timeout_s: float) -> None:
    import fcntl

    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise RefreshLockTimeout(
                    f"refresh lock at fd {fd} not acquired within {timeout_s:.1f}s"
                ) from None
            time.sleep(_POLL_INTERVAL_S)


def _acquire_windows(fd: int, timeout_s: float) -> None:
    import msvcrt

    deadline = time.monotonic() + timeout_s
    while True:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise RefreshLockTimeout(
                    f"refresh lock at fd {fd} not acquired within {timeout_s:.1f}s"
                ) from None
            time.sleep(_POLL_INTERVAL_S)


def _release(fd: int) -> None:
    # Swallow release errors so they never mask an exception raised inside the
    # ``with`` block; the kernel releases the lock when the FD closes anyway.
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


__all__ = ["RefreshLockTimeout", "file_lock", "refresh_lock_path"]
