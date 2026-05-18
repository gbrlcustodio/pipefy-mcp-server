"""Golden ``--help`` output for the full Typer tree (task 12.4 UX consistency lock)."""

from __future__ import annotations

import os
from pathlib import Path

import click
from typer.main import get_command

from pipefy_cli.main import app

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cli_help_golden.txt"
_UPDATE_ENV = "PIPEFY_UPDATE_CLI_HELP_GOLDEN"


def _stable_help_env():
    """Stable terminal size for Rich / Typer across Linux CI and local dev."""
    env = os.environ.copy()
    env["COLUMNS"] = "80"
    env["LINES"] = "24"
    env["TERM"] = "dumb"
    return env


def _normalize_help(text):
    lines = [ln.rstrip() for ln in text.splitlines()]
    body = "\n".join(lines).strip()
    if body:
        return body + "\n"
    return ""


def _walk_commands(path, cmd):
    yield path, cmd
    if isinstance(cmd, click.Group):
        for name in sorted(cmd.commands):
            sub = cmd.commands[name]
            if getattr(sub, "hidden", False):
                continue
            yield from _walk_commands(path + [name], sub)


def _path_key(path):
    return "/".join(path) if path else "_"


def _build_golden_digest(runner):
    root = get_command(app)
    assert isinstance(root, click.Group)
    blocks = []
    for path, _cmd in sorted(_walk_commands([], root), key=lambda pc: _path_key(pc[0])):
        argv = [*path, "--help"] if path else ["--help"]
        result = runner.invoke(
            app, argv, catch_exceptions=False, env=_stable_help_env()
        )
        assert result.exit_code == 0, (
            f"help failed for {argv!r}: stderr={result.stderr!r} stdout={result.stdout!r}"
        )
        key = _path_key(path)
        body = _normalize_help(result.stdout)
        blocks.append(f"### HELP {key}\n{body}")
    return "\n".join(blocks) + "\n"


def test_cli_help_matches_golden(runner, clean_pipefy_env, saved_cwd):
    """Compare aggregated ``--help`` text to ``fixtures/cli_help_golden.txt``.

    Regenerate after intentional CLI help changes::

        PIPEFY_UPDATE_CLI_HELP_GOLDEN=1 uv run pytest packages/cli/tests/test_cli_help_golden.py::test_cli_help_matches_golden -q
    """

    digest = _build_golden_digest(runner)
    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get(_UPDATE_ENV) == "1":
        _FIXTURE.write_text(digest, encoding="utf-8")
    assert _FIXTURE.is_file(), (
        f"Missing golden file {_FIXTURE}. Generate with {_UPDATE_ENV}=1 on the test above."
    )
    expected = _FIXTURE.read_text(encoding="utf-8")
    assert digest == expected, (
        "CLI --help output drifted from golden file. "
        f"If the change is intentional, re-run with {_UPDATE_ENV}=1 to refresh {_FIXTURE.name}."
    )


def test_destructive_commands_document_skip_confirm(
    runner, clean_pipefy_env, saved_cwd
):
    """Destructive flows should document ``--yes`` / ``-y`` in ``--help`` (non-interactive scripts)."""

    root = get_command(app)
    assert isinstance(root, click.Group)
    targets = []
    for path, _cmd in _walk_commands([], root):
        key = _path_key(path)
        if key.endswith("/delete") or key == "member/remove" or key == "graphql/exec":
            targets.append(path)

    missing = []
    for path in sorted(targets, key=_path_key):
        argv = [*path, "--help"]
        result = runner.invoke(
            app, argv, catch_exceptions=False, env=_stable_help_env()
        )
        assert result.exit_code == 0
        out = result.stdout.lower()
        if "--yes" not in out and " -y" not in out and "\n-y" not in out:
            missing.append(_path_key(path))
    assert not missing, (
        "These commands use destructive or guarded flows but --help does not show --yes/-y: "
        + ", ".join(missing)
    )
