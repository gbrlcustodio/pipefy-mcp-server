"""Typer shell completion install/show (bash and zsh) with isolated ``HOME``."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPLETION_OFF = {"_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION": "1"}


def _uv_run_pipefy(
    *args: str,
    cwd: Path,
    env: dict[str, str],
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    uv = shutil.which("uv")
    if not uv:
        pytest.skip("uv not on PATH (required to invoke workspace `pipefy`)")
    return subprocess.run(
        [uv, "run", "pipefy", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_show_completion_bash_prints_snippet():
    env = {**os.environ, **_COMPLETION_OFF}
    result = _uv_run_pipefy("--show-completion", "bash", cwd=_REPO_ROOT, env=env)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "complete -o default" in out
    assert "pipefy" in out


def test_install_completion_bash_writes_script_and_bashrc(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), **_COMPLETION_OFF}
    result = _uv_run_pipefy("--install-completion", "bash", cwd=_REPO_ROOT, env=env)
    assert result.returncode == 0, result.stderr
    script = home / ".bash_completions" / "pipefy.sh"
    assert script.is_file()
    body = script.read_text()
    assert "complete -o default" in body
    bashrc = home / ".bashrc"
    assert bashrc.is_file()
    assert "bash_completions" in bashrc.read_text()


def test_install_completion_zsh_writes_zfunc_and_zshrc(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), **_COMPLETION_OFF}
    result = _uv_run_pipefy("--install-completion", "zsh", cwd=_REPO_ROOT, env=env)
    assert result.returncode == 0, result.stderr
    zfunc = home / ".zfunc" / "_pipefy"
    assert zfunc.is_file()
    assert "#compdef pipefy" in zfunc.read_text()
    zshrc = home / ".zshrc"
    assert zshrc.is_file()
    assert "fpath+=" in zshrc.read_text()
