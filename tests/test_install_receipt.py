"""The install receipt: what ``install.sh`` writes and what ``uninstall.sh`` does with it.

Every run gets a synthetic ``HOME`` and a ``PATH`` built from scratch. ``curl``,
``uv``, ``npx``, ``claude``, ``secret-tool``, ``pipefy`` and ``ps`` are stubs
that append their argv to a log, so no test reaches the network, a real tool
environment, a real keychain, or a real client config.

``install.sh`` had no coverage before this file, so its harness lives here:
fixture-directed runs against those stubs, plus ``--dry-run``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_INSTALL = _REPO_ROOT / "install.sh"
_UNINSTALL = _REPO_ROOT / "uninstall.sh"
# Prefer dash where present: /bin/sh is bash in POSIX mode on macOS, which
# forgives constructs a Debian-family /bin/sh rejects.
_SH = shutil.which("dash") or shutil.which("sh") or "/bin/sh"

_TAG = "v0.5.0"
_BASE_TOOLS = (
    "cat",
    "cp",
    "mv",
    "rm",
    "rmdir",
    "mkdir",
    "chmod",
    "date",
    "sed",
    "head",
    "basename",
    "id",
    "mktemp",
    "readlink",
    "dirname",
    "awk",
    "grep",
    "cut",
    "tr",
    "ls",
    "env",
    "find",
    "python3",
    # install.sh pipes the uv installer into a fresh shell.
    "sh",
)

_RELEASES = json.dumps(
    [
        {"tag_name": f"{_TAG}-alpha.7"},
        {"tag_name": _TAG},
        {"tag_name": "v0.4.0"},
    ],
    indent=2,
)
_RELEASE = json.dumps(
    {
        "tag_name": _TAG,
        "assets": [
            {
                "browser_download_url": (
                    "https://example.com/pipefy_cli-0.5.0-py3-none-any.whl"
                )
            },
            {
                "browser_download_url": (
                    "https://example.com/pipefy_mcp_server-0.5.0-py3-none-any.whl"
                )
            },
            {
                "browser_download_url": (
                    "https://example.com/pipefy-0.5.0-py3-none-any.whl"
                )
            },
        ],
    },
    indent=2,
)

# `curl` answers the two GitHub API calls from fixture files and serves a uv
# installer that drops a `uv` stub into ~/.local/bin, which is how install.sh's
# own "uv was missing" path is exercised without touching astral.sh.
_CURL = """#!/bin/sh
printf '%s\\n' "curl $*" >> "$STUBLOG"
for arg in "$@"; do
    case "$arg" in
        *astral.sh*) cat "$STUBSTATE/uv-installer.sh"; exit 0 ;;
        *releases/tags/*) cat "$STUBSTATE/release.json"; exit 0 ;;
        *releases*) cat "$STUBSTATE/releases.json"; exit 0 ;;
    esac
done
exit 22
"""

_UV = """#!/bin/sh
printf '%s\\n' "uv $*" >> "$STUBLOG"
if [ "$1" = tool ] && [ "$2" = list ]; then
    if [ -f "$STUBSTATE/tools${UV_TOOL_DIR:-}" ]; then
        cat "$STUBSTATE/tools${UV_TOOL_DIR:-}"
    fi
fi
exit 0
"""

_NPX = """#!/bin/sh
printf '%s\\n' "npx $*" >> "$STUBLOG"
for skill in pipefy-tasks pipefy-reports; do
    mkdir -p "$STUBSKILLS/$skill"
    printf -- '---\\nname: x\\n---\\n' > "$STUBSKILLS/$skill/SKILL.md"
done
exit 0
"""

_CLAUDE = """#!/bin/sh
printf '%s\\n' "claude $*" >> "$STUBLOG"
case "$*" in
    "mcp --help") printf '  list\\n  add\\n  remove\\n  logout\\n' ;;
    "plugin --help") printf '  install\\n  uninstall\\n  marketplace\\n' ;;
    "plugin marketplace --help") printf '  add\\n  remove\\n  list\\n' ;;
esac
exit 0
"""

_SECRET_TOOL = """#!/bin/sh
printf '%s\\n' "secret-tool $*" >> "$STUBLOG"
exit 0
"""

_PIPEFY = """#!/bin/sh
printf '%s\\n' "pipefy $*" >> "$STUBLOG"
exit 0
"""


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _home(tmp_path: Path, name: str = "home") -> Path:
    home = tmp_path / name
    home.mkdir(parents=True, exist_ok=True)
    return home


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _stub_path(
    tmp_path: Path, home: Path, *, uv: bool = True, npx: bool = True
) -> Path:
    stub = tmp_path / "stubbin"
    stub.mkdir(parents=True, exist_ok=True)
    state = tmp_path / "stubstate"
    state.mkdir(exist_ok=True)
    for tool in _BASE_TOOLS:
        real = shutil.which(tool)
        if real is None:  # pragma: no cover - depends on the host image
            pytest.skip(f"{tool} not available to stub")
        link = stub / tool
        if not link.exists():
            link.symlink_to(real)
    _write_exec(stub / "uname", '#!/bin/sh\nprintf "%s\\n" "Linux"\n')
    _write_exec(stub / "curl", _CURL)
    _write_exec(stub / "claude", _CLAUDE)
    _write_exec(stub / "secret-tool", _SECRET_TOOL)
    _write_exec(stub / "pipefy", _PIPEFY)
    _write_exec(stub / "ps", "#!/bin/sh\nexit 0\n")
    if uv:
        _write_exec(stub / "uv", _UV)
    if npx:
        _write_exec(stub / "npx", _NPX)
    (state / "releases.json").write_text(_RELEASES, encoding="utf-8")
    (state / "release.json").write_text(_RELEASE, encoding="utf-8")
    # What the uv installer would leave behind: a `uv` on PATH under
    # ~/.local/bin, which is exactly where install.sh looks for it afterwards.
    uv_body = _UV.replace("'", "'\\''")
    (state / "uv-installer.sh").write_text(
        "#!/bin/sh\n"
        f'mkdir -p "{home}/.local/bin"\n'
        f"printf '%s' '{uv_body}' > \"{home}/.local/bin/uv\"\n"
        f'chmod 755 "{home}/.local/bin/uv"\n',
        encoding="utf-8",
    )
    return stub


def _env(tmp_path: Path, home: Path, stub: Path, extra: dict[str, str] | None) -> dict:
    env = {
        "HOME": str(home),
        "PATH": str(stub),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "UV_CACHE_DIR": str(home / "no-such-uv-cache"),
        "STUBLOG": str(tmp_path / "stub.log"),
        "STUBSTATE": str(tmp_path / "stubstate"),
        "STUBSKILLS": str(home / ".claude" / "skills"),
    }
    if extra:
        env.update(extra)
    return env


def _install(
    tmp_path: Path,
    home: Path,
    stub: Path,
    *,
    args: tuple[str, ...] = ("--yes", "--no-skills", "--client", "none"),
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_SH, str(_INSTALL), *args],
        cwd=str(home),
        env=_env(tmp_path, home, stub, env_extra),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _uninstall(
    tmp_path: Path,
    home: Path,
    stub: Path,
    *,
    args: tuple[str, ...] = ("--yes",),
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_SH, str(_UNINSTALL), *args],
        cwd=str(home),
        env=_env(tmp_path, home, stub, env_extra),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _receipt(home: Path) -> Path:
    return home / ".local" / "state" / "pipefy" / "install-receipt"


def _lines(home: Path) -> list[str]:
    return _receipt(home).read_text(encoding="utf-8").splitlines()


def _stubs(tmp_path: Path) -> list[str]:
    log = tmp_path / "stub.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _write_receipt(home: Path, body: str) -> Path:
    path = _receipt(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


_COMPLETE = f"""record=begin
schema=1
time=2026-01-01T00:00:00Z
uv_installed_by_us=false
release_tag={_TAG}
uv_tool=pipefy-cli
uv_tool=pipefy-mcp-server
entry_created.cursor=true
record=end
"""


# --------------------------------------------------------- what install writes


def test_a_finished_install_writes_one_complete_record(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)

    result = _install(tmp_path, home, stub, args=("--yes", "--client", "cursor"))

    assert result.returncode == 0, result.stdout + result.stderr
    lines = _lines(home)
    assert lines[0] == "record=begin"
    assert lines[1] == "schema=1"
    assert lines[-1] == "record=end"
    assert "uv_installed_by_us=false" in lines
    assert f"release_tag={_TAG}" in lines
    assert "uv_tool=pipefy-cli" in lines
    assert "uv_tool=pipefy-mcp-server" in lines
    assert f"skills_dir={home}/.claude/skills" in lines
    assert "entry_created.cursor=true" in lines
    # Recorded only where the installer used one; uv's default needs no note.
    assert not any(line.startswith("uv_tool_dir=") for line in lines)
    assert re.fullmatch(r"time=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", lines[2])
    assert str(_receipt(home)) in result.stdout


def test_a_prefix_is_recorded_and_installs_land_under_it(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    prefix = tmp_path / "elsewhere"

    result = _install(
        tmp_path,
        home,
        stub,
        args=("--yes", "--no-skills", "--client", "none", "--prefix", str(prefix)),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"uv_tool_dir={prefix}" in _lines(home)


@pytest.mark.parametrize(
    "leaf",
    ["with space", "with=equals", "with\nnewline", "with\ttab", "with\\backslash"],
)
def test_a_prefix_needing_escaping_round_trips_through_both_scripts(tmp_path, leaf):
    """A key=value format with no quoting rules has to define its own."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    prefix = tmp_path / f"tools {leaf}"
    prefix.mkdir()
    (tmp_path / "stubstate" / "tools").mkdir(exist_ok=True)
    (tmp_path / "stubstate" / f"tools{prefix}").parent.mkdir(
        parents=True, exist_ok=True
    )
    (tmp_path / "stubstate" / f"tools{prefix}").write_text(
        "pipefy-cli v0.5.0\n", encoding="utf-8"
    )

    result = _install(
        tmp_path,
        home,
        stub,
        args=("--yes", "--no-skills", "--client", "none", "--prefix", str(prefix)),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    body = _receipt(home).read_text(encoding="utf-8")
    # One value, one line: nothing in it escapes onto a line of its own.
    assert "\n" not in body.split("uv_tool_dir=")[1].split("\n")[0].replace("\\n", "")
    for line in body.splitlines():
        assert line.count("=") >= 1 or line == ""

    # The reader is the proof the escaping round-trips: it re-derives the
    # directory and asks uv about that exact one.
    scan = _uninstall(tmp_path, home, stub, args=("--scan",))
    assert f"from the install receipt: {prefix}" in scan.stdout
    assert f"uv tool installed: pipefy-cli (under {prefix})" in scan.stdout


def test_append_only_across_two_runs_with_different_clients(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)

    first = _install(tmp_path, home, stub, args=("--yes", "--client", "cursor"))
    assert first.returncode == 0, first.stdout + first.stderr
    second = _install(tmp_path, home, stub, args=("--yes", "--client", "codex"))
    assert second.returncode == 0, second.stdout + second.stderr

    lines = _lines(home)
    assert lines.count("record=begin") == 2
    assert lines.count("record=end") == 2
    # The first run's answer is still there after the second.
    assert "entry_created.cursor=true" in lines
    assert "entry_created.codex=true" in lines


def test_dry_run_writes_no_receipt(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)

    result = _install(
        tmp_path, home, stub, args=("--dry-run", "--yes", "--client", "cursor")
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not _receipt(home).exists()
    assert not (home / ".local").exists()
    assert f"+ record this run in {_receipt(home)}" in result.stderr
    assert not (home / ".cursor").exists()


def test_uv_installed_by_this_run_is_recorded(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home, uv=False)

    result = _install(tmp_path, home, stub, args=("--yes", "--client", "none"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "uv_installed_by_us=true" in _lines(home)
    assert (home / ".local" / "bin" / "uv").exists()


def test_an_entry_already_present_is_recorded_as_found_not_created(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    theirs = {"mcpServers": {"pipefy": {"command": "their-own-launcher"}}}
    _write_json(home / ".cursor" / "mcp.json", theirs)

    result = _install(tmp_path, home, stub, args=("--yes", "--client", "cursor"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "entry_created.cursor=false" in _lines(home)
    assert json.loads((home / ".cursor" / "mcp.json").read_text()) == theirs


def test_a_codex_section_already_present_is_recorded_as_found(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text(
        '[mcp_servers.pipefy]\ncommand = "pipefy-mcp-server"\n', encoding="utf-8"
    )

    result = _install(tmp_path, home, stub, args=("--yes", "--client", "codex"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "entry_created.codex=false" in _lines(home)


def test_a_crashed_install_leaves_a_truncated_but_usable_record(tmp_path):
    """No `record=end`, and the steps that did happen are still recorded."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home, uv=True)
    # The release resolves, then the wheel install fails, so the run dies
    # between two receipt writes.
    _write_exec(
        stub / "uv",
        '#!/bin/sh\nprintf \'%s\\n\' "uv $*" >> "$STUBLOG"\n'
        'if [ "$1" = tool ] && [ "$2" = install ]; then exit 1; fi\nexit 0\n',
    )

    result = _install(tmp_path, home, stub, args=("--yes", "--client", "cursor"))

    assert result.returncode != 0
    lines = _lines(home)
    assert lines[0] == "record=begin"
    assert f"release_tag={_TAG}" in lines
    assert "record=end" not in lines
    assert not any(line.startswith("uv_tool=") for line in lines)


# ------------------------------------------------------ nothing secret in it


def test_a_credential_in_the_environment_never_reaches_the_receipt(tmp_path):
    sentinel = "s3cr3t-value-do-not-record"
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)

    result = _install(
        tmp_path,
        home,
        stub,
        args=("--yes", "--client", "cursor"),
        env_extra={
            "PIPEFY_TOKEN": sentinel,
            "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET": sentinel,
            "PIPEFY_OAUTH_SECRET": sentinel,
            "UV_TOOL_DIR": str(tmp_path / "tools"),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    body = _receipt(home).read_text(encoding="utf-8")
    assert sentinel not in body
    assert sentinel not in result.stdout
    # The environment did reach the run: the tool directory it named is there.
    assert f"uv_tool_dir={tmp_path}/tools" in body


def test_the_receipt_vocabulary_is_closed(tmp_path):
    """A key the reader does not know is a key that can carry anything.

    The parser drops an unrecognized key, so the guard that keeps a secret out
    of the file is the writer's own fixed vocabulary. This pins it.
    """
    body = _INSTALL.read_text(encoding="utf-8")
    keys = {
        match.group(1) for match in re.finditer(r'receipt_put\s+"?([^"\s(]+)"?', body)
    }
    assert keys == {
        "record",
        "schema",
        "time",
        "uv_tool_dir",
        "uv_installed_by_us",
        "release_tag",
        "uv_tool",
        "skills_dir",
        "skill",
        "entry_created.$1",
    }, sorted(keys)


def test_the_secret_leak_check_has_teeth(tmp_path):
    """Mutate a value into the receipt and both halves of the guard fire.

    The writer's side has to notice a credential reaching the file, and the
    reader's side has to keep an unrecognized value out of its report.
    """
    sentinel = "s3cr3t-value-do-not-record"
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    leaky = tmp_path / "install-leaky.sh"
    body = _INSTALL.read_text(encoding="utf-8")
    anchor = '    receipt_put release_tag "$TAG"\n'
    assert anchor in body
    leaky.write_text(
        body.replace(anchor, anchor + '    receipt_put leaked "${PIPEFY_TOKEN:-}"\n'),
        encoding="utf-8",
    )

    installed = subprocess.run(
        [_SH, str(leaky), "--yes", "--no-skills", "--client", "none"],
        cwd=str(home),
        env=_env(tmp_path, home, stub, {"PIPEFY_TOKEN": sentinel}),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    # The check is not vacuous: a leak really does land in the file.
    assert f"leaked={sentinel}" in _lines(home)

    scan = _uninstall(tmp_path, home, stub, args=("--scan",))
    assert sentinel not in scan.stdout
    assert sentinel not in scan.stderr


# ------------------------------------------------- what uninstall makes of it


def test_no_receipt_means_heuristic_mode_and_it_says_so(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)

    scan = _uninstall(tmp_path, home, stub, args=("--scan",))

    # 1, not 0: the stub PATH carries a `pipefy` binary, which is a finding.
    assert scan.returncode == 1, scan.stdout + scan.stderr
    assert f"no install receipt at {_receipt(home)}" in scan.stdout
    assert "Heuristic mode." in scan.stdout
    assert "uv is never treated as this toolkit's" in scan.stdout
    assert "not a" in scan.stdout and "migration step" in scan.stdout


def test_heuristic_mode_removes_an_installer_shaped_entry_and_leaves_the_rest(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    _write_json(
        home / ".cursor" / "mcp.json",
        {
            "mcpServers": {
                "pipefy": {"command": "pipefy-mcp-server"},
                "pipefy-dev": {"command": "uvx", "args": ["pipefy-mcp-server"]},
            }
        },
    )

    run = _uninstall(tmp_path, home, stub)

    left = json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"]
    assert sorted(left) == ["pipefy-dev"]
    assert "is not the single command install.sh writes" in run.stdout


def test_entry_created_true_removes_the_client_entry(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    # Not the installer's shape, so only the receipt can authorise this.
    _write_json(
        home / ".cursor" / "mcp.json",
        {"mcpServers": {"pipefy": {"command": "uvx", "args": ["pipefy-mcp-server"]}}},
    )
    _write_receipt(home, _COMPLETE)

    run = _uninstall(tmp_path, home, stub)

    assert json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"] == {}
    assert "created the 'pipefy' registration in the cursor config" in run.stdout


def test_entry_created_false_leaves_the_client_entry_alone(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    # The installer's own shape, which heuristic mode would have removed.
    theirs = {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}}
    _write_json(home / ".cursor" / "mcp.json", theirs)
    _write_receipt(
        home,
        _COMPLETE.replace("entry_created.cursor=true", "entry_created.cursor=false"),
    )

    run = _uninstall(tmp_path, home, stub)

    assert json.loads((home / ".cursor" / "mcp.json").read_text()) == theirs
    assert "was already registered when install.sh ran" in run.stdout


def test_a_codex_section_the_installer_found_is_left_alone(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir(parents=True)
    before = '[mcp_servers.pipefy]\ncommand = "pipefy-mcp-server"\n'
    codex.write_text(before, encoding="utf-8")
    _write_receipt(
        home,
        _COMPLETE.replace("entry_created.cursor=true", "entry_created.codex=false"),
    )

    run = _uninstall(tmp_path, home, stub)

    assert codex.read_text(encoding="utf-8") == before
    assert "was already there when install.sh ran" in run.stdout


def test_the_receipt_is_removed_by_teardown(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    _write_receipt(home, _COMPLETE)

    run = _uninstall(tmp_path, home, stub)

    assert "delete the install receipt" in run.stdout
    assert not _receipt(home).exists()
    # And the state directory it lived in, now that nothing else is in it.
    assert not (home / ".local" / "state" / "pipefy").exists()


def test_a_recorded_tool_directory_is_uninstalled_under_that_prefix(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    prefix = tmp_path / "prefixed tools"
    prefix.mkdir()
    listing = tmp_path / "stubstate" / f"tools{prefix}"
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text("pipefy-cli v0.5.0\n", encoding="utf-8")
    _write_receipt(
        home, _COMPLETE.replace("schema=1\n", f"schema=1\nuv_tool_dir={prefix}\n")
    )

    run = _uninstall(tmp_path, home, stub)

    assert f"uv tool installed: pipefy-cli (under {prefix})" in run.stdout
    trace = [line[2:] for line in run.stderr.splitlines() if line.startswith("+ ")]
    assert "uv tool uninstall pipefy-cli" in trace


def test_two_prefixes_are_both_torn_down(tmp_path):
    """Append-only means two runs disagree, and the merge takes the union.

    Both runs really did create tool environments; keeping only the newer
    prefix would strand the older one exactly as having no receipt does.
    """
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    first = tmp_path / "tools-a"
    second = tmp_path / "tools-b"
    for prefix in (first, second):
        prefix.mkdir()
        listing = tmp_path / "stubstate" / f"tools{prefix}"
        listing.parent.mkdir(parents=True, exist_ok=True)
        listing.write_text("pipefy-cli v0.5.0\n", encoding="utf-8")
    _write_receipt(
        home,
        f"record=begin\nschema=1\nuv_tool_dir={first}\nrecord=end\n"
        f"record=begin\nschema=1\nuv_tool_dir={second}\nrecord=end\n",
    )

    run = _uninstall(tmp_path, home, stub, args=("--dry-run",))

    assert f"uv tool uninstall pipefy-cli, under {first}" in run.stdout
    assert f"uv tool uninstall pipefy-cli, under {second}" in run.stdout


def test_a_recorded_tool_directory_that_is_gone_is_reported_not_used(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    missing = tmp_path / "gone"
    _write_receipt(
        home, _COMPLETE.replace("schema=1\n", f"schema=1\nuv_tool_dir={missing}\n")
    )

    scan = _uninstall(tmp_path, home, stub, args=("--scan",))

    assert f"records a tool directory that is gone: {missing}" in scan.stdout


def test_a_recorded_skills_directory_is_swept(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    elsewhere = tmp_path / "other skills"
    (elsewhere / "pipefy-tasks").mkdir(parents=True)
    (elsewhere / "pipefy-tasks" / "SKILL.md").write_text("---\n", encoding="utf-8")
    _write_receipt(
        home,
        _COMPLETE.replace(
            "schema=1\n", f"schema=1\nskills_dir={elsewhere}\nskill=pipefy-tasks\n"
        ),
    )

    run = _uninstall(tmp_path, home, stub)

    assert f"1 pipefy-* skills from this toolkit under {elsewhere}" in run.stdout
    assert not (elsewhere / "pipefy-tasks").exists()


def test_the_receipt_reports_what_it_recorded(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    _write_receipt(
        home, _COMPLETE.replace("uv_installed_by_us=false", "uv_installed_by_us=true")
    )

    scan = _uninstall(tmp_path, home, stub, args=("--scan",))

    assert "1 install run(s) recorded" in scan.stdout
    assert f"release: {_TAG}" in scan.stdout
    assert "installed as a uv tool: pipefy-cli" in scan.stdout
    assert "uv was installed by one of those runs" in scan.stdout
    assert "It is still not removed" in scan.stdout


# ------------------------------------------------------------ trust boundary


def test_a_truncated_final_line_still_yields_the_earlier_records(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    _write_receipt(
        home,
        _COMPLETE + "record=begin\nschema=1\nuv_tool=pipefy-cli\nrelease_ta",
    )

    scan = _uninstall(tmp_path, home, stub, args=("--scan",))

    assert "2 install run(s) recorded" in scan.stdout
    assert "1 of them stop mid-record" in scan.stdout
    # The complete record before it is intact and still drives the report.
    assert f"release: {_TAG}" in scan.stdout
    assert "created the 'pipefy' registration in the cursor config" in scan.stdout


def test_a_newer_schema_record_is_skipped_whole(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    theirs = {
        "mcpServers": {"pipefy": {"command": "uvx", "args": ["pipefy-mcp-server"]}}
    }
    _write_json(home / ".cursor" / "mcp.json", theirs)
    _write_receipt(
        home,
        "record=begin\nschema=99\nentry_created.cursor=true\nrecord=end\n",
    )

    run = _uninstall(tmp_path, home, stub)

    assert "written by a newer schema than this script reads" in run.stdout
    # Skipped whole: the entry it claimed to have created is not removed.
    assert json.loads((home / ".cursor" / "mcp.json").read_text()) == theirs


@pytest.mark.parametrize(
    "body",
    [
        "",
        "garbage with no equals sign\n",
        "entry_created.cursor=true\n",  # no record=begin
        "record=begin\nentry_created.cursor=true\nrecord=end\n",  # no schema
        "record=begin\nschema=notanumber\nentry_created.cursor=true\nrecord=end\n",
        "record=begin\nschema=0\nentry_created.cursor=true\nrecord=end\n",
        "record=begin\nschema=1\nENTRY_CREATED.CURSOR=true\nrecord=end\n",
        "\x00\x01\x02binary junk\n",
    ],
)
def test_a_corrupt_receipt_never_widens_what_teardown_deletes(tmp_path, body):
    """A receipt can only ever authorise less than the structural scan found."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    theirs = {
        "mcpServers": {"pipefy": {"command": "uvx", "args": ["pipefy-mcp-server"]}}
    }
    _write_json(home / ".cursor" / "mcp.json", theirs)
    _write_receipt(home, body)

    run = _uninstall(tmp_path, home, stub)

    assert run.returncode in (0, 1), run.stdout + run.stderr
    assert json.loads((home / ".cursor" / "mcp.json").read_text()) == theirs
    assert "is not the single command install.sh writes" in run.stdout


def test_a_value_holding_an_escape_the_writer_never_emits_is_dropped(tmp_path):
    """`\\c` truncates printf %b output, so a value carrying one is not expanded."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    _write_receipt(
        home,
        f"record=begin\nschema=1\nuv_tool_dir={tmp_path}\\ctools\nrecord=end\n",
    )

    scan = _uninstall(tmp_path, home, stub, args=("--scan",))

    assert "1 lines are malformed and were dropped" in scan.stdout
    assert "from the install receipt" not in scan.stdout


def test_a_receipt_naming_a_directory_never_becomes_a_deletion_target(tmp_path):
    """The receipt picks what to ask uv about, never what to remove."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    precious = tmp_path / "precious"
    (precious / "keep-me").mkdir(parents=True)
    _write_receipt(
        home,
        f"record=begin\nschema=1\nuv_tool_dir={precious}\nskills_dir={precious}\n"
        "record=end\n",
    )

    run = _uninstall(tmp_path, home, stub)

    assert (precious / "keep-me").exists()
    trace = [line[2:] for line in run.stderr.splitlines() if line.startswith("+ ")]
    assert all(str(precious) not in line for line in trace if line.startswith("rm")), (
        trace
    )


def test_an_unreadable_receipt_is_reported_rather_than_ignored(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    path = _write_receipt(home, _COMPLETE)
    path.chmod(0o000)
    try:
        scan = _uninstall(tmp_path, home, stub, args=("--scan",))
    finally:
        path.chmod(0o600)

    if os.getuid() == 0:  # pragma: no cover - root reads everything
        pytest.skip("root can read a 000 file")
    assert scan.returncode == 2
    assert "exists but could not be read" in scan.stdout


def test_the_receipt_honours_xdg_state_home(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    state = tmp_path / "xdg state"

    result = _install(
        tmp_path,
        home,
        stub,
        args=("--yes", "--no-skills", "--client", "none"),
        env_extra={"XDG_STATE_HOME": str(state)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (state / "pipefy" / "install-receipt").exists()
    assert not _receipt(home).exists()

    scan = _uninstall(
        tmp_path, home, stub, args=("--scan",), env_extra={"XDG_STATE_HOME": str(state)}
    )
    assert str(state / "pipefy" / "install-receipt") in scan.stdout


def test_the_receipt_is_not_in_the_config_directory(tmp_path):
    """It is installer state; ~/.config/pipefy is the user's, and is emptied."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)

    result = _install(tmp_path, home, stub, args=("--yes", "--client", "none"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (home / ".config" / "pipefy").exists()

    # And teardown still ends with the config directory in the right state: it
    # was never created here, and the receipt did not create it either.
    run = _uninstall(tmp_path, home, stub)
    assert not (home / ".config" / "pipefy").exists()
    assert "not a file this toolkit writes" not in run.stdout


# --------------------------------------------------------- end-to-end round trip


def test_install_then_uninstall_removes_what_the_install_created(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    (tmp_path / "stubstate" / "tools").write_text(
        "pipefy-cli v0.5.0\npipefy-mcp-server v0.5.0\n", encoding="utf-8"
    )

    installed = _install(tmp_path, home, stub, args=("--yes", "--client", "cursor"))
    assert installed.returncode == 0, installed.stdout + installed.stderr
    assert json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"] == {
        "pipefy": {"command": "pipefy-mcp-server"}
    }
    assert (home / ".claude" / "skills" / "pipefy-tasks" / "SKILL.md").exists()

    removed = _uninstall(tmp_path, home, stub)

    assert removed.returncode in (0, 1), removed.stdout + removed.stderr
    assert json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"] == {}
    assert not (home / ".claude" / "skills" / "pipefy-tasks").exists()
    assert not _receipt(home).exists()
    assert "uv tool uninstall pipefy-cli" in _stubs(tmp_path)
    assert "uv tool uninstall pipefy-mcp-server" in _stubs(tmp_path)


def test_the_receipt_records_only_the_skills_this_run_added(tmp_path):
    """A skill under the same name prefix that was already here is not the
    installer's, and teardown reads these names to decide what it may delete."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    mine = home / ".claude" / "skills" / "pipefy-mine"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("---\nname: mine\n---\n", encoding="utf-8")

    result = _install(tmp_path, home, stub, args=("--yes", "--client", "none"))

    assert result.returncode == 0, result.stdout + result.stderr
    lines = _lines(home)
    # Exactly what the `npx skills add` stub writes, and nothing else here.
    assert sorted(line for line in lines if line.startswith("skill=")) == [
        "skill=pipefy-reports",
        "skill=pipefy-tasks",
    ]

    removed = _uninstall(tmp_path, home, stub)

    assert (mine / "SKILL.md").exists()
    assert not (home / ".claude" / "skills" / "pipefy-tasks").exists()
    assert "nothing records where it came from" in removed.stdout


def test_a_claude_desktop_entry_the_installer_found_is_not_removed(tmp_path):
    """The receipt key carries a hyphen, so the reader's alphabet has to.

    A key the reader junks takes the whole "this was already here" bit with it,
    and an installer-shaped entry the user wrote first is then deleted.
    """
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    _write_exec(stub / "uname", '#!/bin/sh\nprintf "%s\\n" "Darwin"\n')
    _write_exec(
        stub / "security",
        '#!/bin/sh\n[ "$1" = find-generic-password ] && exit 44\nexit 0\n',
    )
    config = (
        home
        / "Library"
        / "Application Support"
        / "Claude"
        / "claude_desktop_config.json"
    )
    before = {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}}
    _write_json(config, before)
    _write_receipt(
        home,
        _COMPLETE.replace(
            "entry_created.cursor=true", "entry_created.claude-desktop=false"
        ),
    )

    run = _uninstall(tmp_path, home, stub)

    assert json.loads(config.read_text(encoding="utf-8")) == before
    assert "was already registered when install.sh ran" in run.stdout
    # A junked key would also have been counted as a malformed line.
    assert "lines are malformed" not in run.stdout


def test_the_merge_leaves_utf8_siblings_literal(tmp_path):
    """Adding one server is not licence to rewrite another server's bytes."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, home)
    config = home / ".cursor" / "mcp.json"
    _write_json(config, {"mcpServers": {"café": {"command": "naïve-server"}}})

    result = _install(tmp_path, home, stub, args=("--yes", "--client", "cursor"))

    assert result.returncode == 0, result.stdout + result.stderr
    raw = config.read_text(encoding="utf-8")
    assert "café" in raw and "naïve-server" in raw
    assert "\\u" not in raw
