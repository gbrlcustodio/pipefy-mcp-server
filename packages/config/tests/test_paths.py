"""Tests for ``pipefy_config.paths``."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pipefy_config.paths import config_dir, config_file_path


def test_config_dir_posix_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    assert config_dir() == tmp_path / ".config" / "pipefy"


def test_config_dir_posix_xdg_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config_dir() == tmp_path / "xdg" / "pipefy"


def test_config_dir_windows_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    assert config_dir() == tmp_path / "AppData" / "Roaming" / "pipefy"


def test_config_dir_windows_appdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    assert config_dir() == tmp_path / "appdata" / "pipefy"


def test_config_file_path_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("PIPEFY_CONFIG_FILE", raising=False)
    assert config_file_path() == tmp_path / "pipefy" / "config.toml"


def test_config_file_path_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    override = tmp_path / "alt" / "custom.toml"
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(override))
    assert config_file_path() == override


def test_config_file_path_blank_env_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", "")
    assert config_file_path() == tmp_path / "pipefy" / "config.toml"
