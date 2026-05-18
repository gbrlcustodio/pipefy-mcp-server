"""``pipefy --version`` prints the installed CLI version and exits cleanly."""

from __future__ import annotations

from pipefy_cli import __version__
from pipefy_cli.main import app


def test_version_flag_prints_and_exits(runner, clean_pipefy_env, saved_cwd):
    """``--version`` is eager — it must not require auth or settings.

    The release smoke (`uvx --from git+... pipefy-cli --version`) relies on this
    flag returning the version without booting the auth/OAuth stack, so we
    invoke it with no PIPEFY_* env vars set (``clean_pipefy_env``).
    """
    result = runner.invoke(app, ["--version"], catch_exceptions=False)
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
