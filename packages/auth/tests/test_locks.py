"""Tests for the cross-process refresh lock helpers."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from pipefy_auth.locks import RefreshLockTimeout, file_lock, refresh_lock_path


@pytest.mark.unit
def test_file_lock_happy_path(tmp_path: Path) -> None:
    """``file_lock`` returns cleanly and leaves the lock file on disk."""
    lock = tmp_path / "x.lock"
    with file_lock(lock):
        pass
    assert lock.exists()


@pytest.mark.unit
def test_file_lock_reentrancy_after_release(tmp_path: Path) -> None:
    """A second acquire on the same path succeeds after the first releases."""
    lock = tmp_path / "x.lock"
    with file_lock(lock):
        pass
    with file_lock(lock, timeout_s=1.0):
        pass


@pytest.mark.unit
def test_file_lock_contention_times_out(tmp_path: Path) -> None:
    """A second acquirer raises ``RefreshLockTimeout`` while the first holds the lock."""
    lock = tmp_path / "x.lock"
    holder_acquired = threading.Event()
    holder_release = threading.Event()

    def hold_lock() -> None:
        with file_lock(lock, timeout_s=5.0):
            holder_acquired.set()
            holder_release.wait(timeout=5.0)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    try:
        assert holder_acquired.wait(timeout=2.0), "holder thread never acquired"
        with pytest.raises(RefreshLockTimeout):
            with file_lock(lock, timeout_s=0.2):
                pass
    finally:
        holder_release.set()
        holder.join(timeout=2.0)


@pytest.mark.unit
@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "POSIX-only: fcntl.flock is released on FD close by the kernel even on "
        "SIGKILL. Windows mandatory locking has a different recovery shape and "
        "is backstopped by timeout_s rather than tested here."
    ),
)
def test_file_lock_released_after_sigkill(tmp_path: Path) -> None:
    """A subprocess that holds the lock and is SIGKILLed releases it via FD close."""
    lock = tmp_path / "x.lock"
    ready = tmp_path / "ready"

    script = (
        "import os, sys, time\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, %r)\n"
        "from pipefy_auth.locks import file_lock\n"
        "with file_lock(Path(%r)):\n"
        "    Path(%r).touch()\n"
        "    time.sleep(30)\n"
    ) % (str(Path(__file__).parents[2] / "src"), str(lock), str(ready))

    proc = subprocess.Popen([sys.executable, "-c", script])
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if ready.exists():
                break
            time.sleep(0.05)
        assert ready.exists(), "subprocess never acquired the lock"

        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=2.0)

        with file_lock(lock, timeout_s=2.0):
            pass
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2.0)


@pytest.mark.unit
def test_refresh_lock_path_is_pure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``refresh_lock_path()`` resolves the path without touching the filesystem."""
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    expected_dir = fake_home / ".config" / "pipefy"
    path = refresh_lock_path()
    assert path == expected_dir / "refresh.lock"
    assert not expected_dir.exists()


@pytest.mark.unit
def test_file_lock_creates_parent_dir(tmp_path: Path) -> None:
    """``file_lock`` creates the lock file's parent dir on first acquire."""
    lock = tmp_path / "fresh" / "subdir" / "x.lock"
    assert not lock.parent.exists()
    with file_lock(lock):
        pass
    assert lock.parent.is_dir()
    assert lock.exists()
