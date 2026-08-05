"""``install.sh`` and ``uninstall.sh`` cannot drift apart.

Both halves are observed, never read out of the sources. What the installer
writes is the difference between two snapshots of a fixture ``HOME`` taken
around a real run; what the teardown accounts for is what a real
``uninstall.sh --yes`` against that same ``HOME`` leaves behind. A path a new
installer step creates therefore has to be reachable by the teardown or this
fails, and no one has to keep a hand-written inventory in step.

The stub ``PATH`` and the fixture ``HOME`` come from ``test_install_receipt``,
which is where ``install.sh``'s harness lives.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest
from test_install_receipt import (
    _INSTALL,
    _SH,
    _UNINSTALL,
    _env,
    _home,
    _install,
    _receipt,
    _stub_path,
    _stubs,
    _uninstall,
    _write_exec,
)

_GUARD_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "scripts"
    / "check_deletion_guard.py"
)
_spec = importlib.util.spec_from_file_location("check_deletion_guard", _GUARD_SCRIPT)
assert _spec is not None and _spec.loader is not None
_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_guard)

# `security` reports an empty keychain, so a Darwin run reaches the same end
# state as a Linux one without a source going uninspected.
_SECURITY = """#!/bin/sh
printf '%s\\n' "security $*" >> "$STUBLOG"
[ "$1" = find-generic-password ] && exit 44
exit 0
"""

# Per client: the `uname -s` the run reports, and the config file install.sh
# writes there. `None` means the client gets no file — claude-code prints slash
# commands for the user to type, and `none` prints a snippet to paste.
_CLIENTS = (
    ("none", "Linux", None),
    ("claude-code", "Linux", None),
    ("cursor", "Linux", ".cursor/mcp.json"),
    ("codex", "Linux", ".codex/config.toml"),
    (
        "claude-desktop",
        "Darwin",
        "Library/Application Support/Claude/claude_desktop_config.json",
    ),
)

# The two kinds of file a completed teardown deliberately leaves behind. Each
# is a decision, not an oversight, so each is spelled out rather than globbed.
#
# A client's config is the client's file even when this toolkit created it: the
# teardown removes the registration it made and leaves the file, because by the
# time anyone tears down it may hold other servers. The assertion below is
# therefore not "the file is gone" but "the registration is".
#
# The backup is the copy `backup_file` takes before editing a file the user
# owns; deleting it would defeat the point of taking it.
_BACKUP = re.compile(r"\.bak\.[0-9]+$")


def _files(home: Path) -> set[str]:
    return {
        str(path.relative_to(home))
        for path in home.rglob("*")
        if path.is_file() or path.is_symlink()
    }


def _unexplained(written: set[str], config: str | None) -> list[str]:
    """Files still in ``HOME`` after teardown that nothing accounts for."""
    allowed = {config} if config is not None else set()
    return sorted(
        path for path in written if path not in allowed and not _BACKUP.search(path)
    )


def _darwin(stub: Path) -> None:
    _write_exec(stub / "uname", '#!/bin/sh\nprintf "%s\\n" "Darwin"\n')
    _write_exec(stub / "security", _SECURITY)


def _help(script: Path) -> str:
    result = subprocess.run(
        [_SH, str(script), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return result.stdout


def _client_ids(help_text: str) -> set[str]:
    """The `--client` values a script advertises, from its own help output.

    Both scripts print one `One of: ...` line, and `uninstall.sh` generates
    its copy from the client table, so this reads the interface rather than
    the source.
    """
    for line in help_text.splitlines():
        if "One of:" in line:
            return set(re.findall(r"[a-z][a-z-]+", line.split("One of:", 1)[1]))
    raise AssertionError(f"no 'One of:' line in:\n{help_text}")


# ------------------------------------------------------- the write set, per client


@pytest.mark.parametrize(("client", "uname", "config"), _CLIENTS, ids=lambda v: str(v))
def test_every_file_the_installer_writes_is_accounted_for_by_the_teardown(
    tmp_path, client, uname, config
):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    if uname == "Darwin":
        _darwin(stub)
    (tmp_path / "stubstate" / "tools").write_text(
        "pipefy-cli v0.5.0\npipefy-mcp-server v0.5.0\n", encoding="utf-8"
    )
    before = _files(home)

    installed = _install(tmp_path, home, stub, args=("--yes", "--client", client))
    assert installed.returncode == 0, installed.stdout + installed.stderr
    written = _files(home) - before
    # The check has teeth only if the run wrote something: the receipt always,
    # the skills the stub `npx` lays down, and the client's config where the
    # client has one.
    assert str(_receipt(home).relative_to(home)) in written
    assert ".claude/skills/pipefy-tasks/SKILL.md" in written, sorted(written)
    if config is not None:
        assert config in written, sorted(written)

    removed = _uninstall(tmp_path, home, stub)
    assert removed.returncode in (0, 1), removed.stdout + removed.stderr

    unexplained = _unexplained(_files(home) - before, config)
    assert not unexplained, (
        f"install.sh --client {client} wrote these and uninstall.sh left them:\n"
        + "\n".join(unexplained)
        + "\n\nteardown output:\n"
        + removed.stdout
    )
    if config is not None:
        # Left on purpose, but emptied of us.
        body = (home / config).read_text(encoding="utf-8")
        assert "pipefy-mcp-server" not in body, body


# ------------------------------------------------------------- the client tables


def test_every_client_the_installer_writes_for_has_a_row_in_the_teardown_table():
    install_ids = _client_ids(_help(_INSTALL))
    uninstall_ids = _client_ids(_help(_UNINSTALL))

    # `none` is an installer-only choice: it writes no config, so the teardown
    # table has nothing to hold for it.
    assert install_ids - {"none"} <= uninstall_ids, sorted(install_ids - uninstall_ids)
    # And the round trip above covers all of them.
    assert install_ids == {client for client, _, _ in _CLIENTS}


@pytest.mark.parametrize(("client", "uname", "config"), _CLIENTS, ids=lambda v: str(v))
def test_the_advertised_client_values_are_the_accepted_ones(
    tmp_path, client, uname, config
):
    """Help text that named a value neither script took would make the check above vacuous."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    if uname == "Darwin":
        _darwin(stub)

    installed = _install(
        tmp_path, home, stub, args=("--dry-run", "--yes", "--client", client)
    )
    assert "Invalid --client" not in installed.stderr

    if client == "none":
        return
    scanned = _uninstall(tmp_path, home, stub, args=("--scan", "--client", client))
    assert "Invalid --client" not in scanned.stderr


# ------------------------------------------------------------------- the dry run


@pytest.mark.parametrize(("client", "uname", "config"), _CLIENTS, ids=lambda v: str(v))
def test_a_dry_run_previews_every_client_and_writes_nothing(
    tmp_path, client, uname, config
):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    if uname == "Darwin":
        _darwin(stub)
    before = _files(home)

    result = _install(
        tmp_path, home, stub, args=("--dry-run", "--yes", "--client", client)
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert _files(home) == before
    assert not _receipt(home).exists()


def test_claude_desktop_is_refused_on_linux_rather_than_previewed(tmp_path):
    """The one client with no build for the platform, and the installer says so."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)

    result = _install(
        tmp_path, home, stub, args=("--dry-run", "--yes", "--client", "claude-desktop")
    )

    assert result.returncode == 1
    assert "Claude Desktop has no Linux build" in result.stderr
    assert _files(home) == set()


# ------------------------------------------------------------------- the uv tools


def test_every_tool_the_receipt_records_is_uninstalled_by_name(tmp_path):
    """A uv tool leaves no path in ``HOME``, so the snapshot above cannot see it.

    The installer records each one it installed; the teardown has to ask uv
    about that same name.
    """
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    (tmp_path / "stubstate" / "tools").write_text(
        "pipefy-cli v0.5.0\npipefy-mcp-server v0.5.0\n", encoding="utf-8"
    )

    installed = _install(tmp_path, home, stub, args=("--yes", "--client", "cursor"))
    assert installed.returncode == 0, installed.stdout + installed.stderr
    tools = [
        line.split("=", 1)[1]
        for line in _receipt(home).read_text(encoding="utf-8").splitlines()
        if line.startswith("uv_tool=")
    ]
    assert tools

    _uninstall(tmp_path, home, stub)

    log = _stubs(tmp_path)
    for tool in tools:
        assert f"uv tool uninstall {tool}" in log, log


def test_the_registration_the_installer_writes_is_the_one_teardown_removes(tmp_path):
    """Matched on what it runs: the command in the config is the server binary."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)

    _install(tmp_path, home, stub, args=("--yes", "--no-skills", "--client", "cursor"))
    entry = json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"]
    assert entry == {"pipefy": {"command": "pipefy-mcp-server"}}

    scan = _uninstall(tmp_path, home, stub, args=("--scan",))

    assert "named 'pipefy'" in scan.stdout
    assert str(home / ".cursor" / "mcp.json") in scan.stdout


def test_the_leftover_check_has_teeth(tmp_path):
    """A write the teardown knows nothing about has to fail the round trip."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    body = _INSTALL.read_text(encoding="utf-8")
    anchor = '    receipt_put release_tag "$TAG"\n'
    assert anchor in body
    rogue = tmp_path / "install-rogue.sh"
    rogue.write_text(
        body.replace(
            anchor,
            anchor + '    mkdir -p "$HOME/.pipefy-rogue"\n'
            '    : > "$HOME/.pipefy-rogue/state"\n',
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [_SH, str(rogue), "--yes", "--no-skills", "--client", "none"],
        cwd=str(home),
        env=_env(tmp_path, home, stub, None),
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    _uninstall(tmp_path, home, stub)

    assert _unexplained(_files(home), None) == [".pipefy-rogue/state"]


# --------------------------------------------------------------- deletion guard


def test_every_deletion_routes_through_the_guard():
    assert _guard.check(_UNINSTALL) == []


@pytest.mark.parametrize(
    "mutation",
    [
        # A deletion that skipped the guard entirely.
        ("act_rmdir() {\n", 'act_rmdir() {\n    rm -rf "$1"\n'),
        # A guard that stopped refusing the argument that matters most.
        ('[ "$_rp" != "$HOME" ] || err "refusing to remove \\$HOME ($HOME)"', ""),
    ],
    ids=["unguarded-rm", "dropped-refusal"],
)
def test_the_deletion_guard_check_has_teeth(tmp_path, mutation):
    anchor, replacement = mutation
    body = _UNINSTALL.read_text(encoding="utf-8")
    assert anchor in body
    mutated = tmp_path / "uninstall.sh"
    mutated.write_text(body.replace(anchor, replacement), encoding="utf-8")

    assert _guard.check(mutated) != []


def test_a_case_label_is_not_read_as_a_deletion():
    """`rmdir)` dispatches an action kind; the check must not trip on it."""
    body = _UNINSTALL.read_text(encoding="utf-8")
    assert "        rmdir) act_rmdir" in body
    assert _guard.check(_UNINSTALL) == []
