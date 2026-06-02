"""Tests for ``pipefy_infra.filesystem.LocalFile``."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipefy_infra.filesystem import LocalFile, LocalFileError


@pytest.mark.unit
def test_local_file_read_happy_path(tmp_path: Path):
    f = tmp_path / "hello.txt"
    f.write_bytes(b"hi")
    file = LocalFile(f)
    file.read()
    assert file.path == f
    assert file.bytes == b"hi"
    assert file.size == 2
    assert file.name == "hello.txt"


@pytest.mark.unit
def test_local_file_properties_raise_before_read(tmp_path: Path):
    """Accessing path/bytes before read() is a programming error."""
    file = LocalFile(tmp_path / "nope")
    with pytest.raises(RuntimeError, match="read"):
        _ = file.path
    with pytest.raises(RuntimeError, match="read"):
        _ = file.bytes


@pytest.mark.unit
def test_local_file_expands_tilde(tmp_path: Path, monkeypatch):
    """``~`` resolves against $HOME; the expanded path is exposed via .path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "h.bin").write_bytes(b"home")
    file = LocalFile(Path("~/h.bin"))
    file.read()
    assert file.path == tmp_path / "h.bin"
    assert file.bytes == b"home"


@pytest.mark.unit
def test_local_file_unknown_user_raises_normalized_error():
    """`~ghostuser/...` raises RuntimeError from expanduser; normalized to LocalFileError."""
    file = LocalFile(Path("~ghost_user_does_not_exist_xyz/foo.bin"))
    with pytest.raises(LocalFileError, match="Cannot expand"):
        file.read()


@pytest.mark.unit
def test_local_file_missing(tmp_path: Path):
    file = LocalFile(tmp_path / "nope.bin")
    with pytest.raises(LocalFileError, match="not found"):
        file.read()


@pytest.mark.unit
def test_local_file_directory(tmp_path: Path):
    file = LocalFile(tmp_path)
    with pytest.raises(LocalFileError, match="not found"):
        file.read()


@pytest.mark.unit
def test_local_file_oversize_when_cap_set(tmp_path: Path):
    """A configured ``max_size_bytes`` rejects files past the cap before reading."""
    f = tmp_path / "big.bin"
    f.write_bytes(b"too-many-bytes")
    file = LocalFile(f, max_size_bytes=4)
    with pytest.raises(LocalFileError, match="too large"):
        file.read()


@pytest.mark.unit
def test_local_file_no_cap_by_default(tmp_path: Path):
    """Without a cap, large files read fine."""
    f = tmp_path / "data.bin"
    f.write_bytes(b"plenty of bytes here")
    file = LocalFile(f)
    file.read()
    assert file.bytes == b"plenty of bytes here"


@pytest.mark.unit
@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses chmod restrictions")
def test_local_file_permission_denied(tmp_path: Path):
    f = tmp_path / "locked.bin"
    f.write_bytes(b"secret")
    f.chmod(0o000)
    file = LocalFile(f)
    try:
        with pytest.raises(LocalFileError, match="Permission denied"):
            file.read()
    finally:
        f.chmod(0o644)
