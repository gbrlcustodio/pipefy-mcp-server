"""``uninstall.sh``'s destructive path, against fixture homes and stub commands.

Every run gets a synthetic ``HOME`` and a ``PATH`` built from scratch. ``uv``,
``claude``, ``security``, ``secret-tool``, ``pipefy`` and ``ps`` are stubs that
append their argv to a log, so no test touches a real keychain, a real client
config, or a real tool environment.

Two independent traces are asserted. The stub log records what external
commands were called with; the ``+ `` lines the script writes to stderr record
every command it ran, including its own ``rm`` and ``cp``. Ordering is the part
that matters most and no filesystem check can see it.
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
_SCRIPT = _REPO_ROOT / "uninstall.sh"
# Prefer dash where present: /bin/sh is bash in POSIX mode on macOS, which
# forgives constructs a Debian-family /bin/sh rejects.
_SH = shutil.which("dash") or shutil.which("sh") or "/bin/sh"

_BASE_TOOLS = (
    "cat",
    "cp",
    "mv",
    "rm",
    "rmdir",
    "mkdir",
    "date",
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
)


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    return home


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# Each stub logs "<name> <argv>" and exits 0. `claude` answers the capability
# probes, `pipefy` reproduces the observed side effect of `auth logout`:
# it recreates the config directory with a fresh lock file.
_UV = """#!/bin/sh
printf '%s\\n' "uv $*" >> "$STUBLOG"
if [ "$1" = tool ] && [ "$2" = list ]; then
    printf 'pipefy-cli v0.0.0\\npipefy-mcp-server v0.0.0\\n'
fi
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

# Like `_CLAUDE`, but `mcp remove` really does edit the config, so a teardown
# can reach a state the re-scan calls clean. That is what isolates the OAuth
# store: it is the one clear the re-scan cannot check either way.
_CLAUDE_THAT_REMOVES = """#!/bin/sh
printf '%s\\n' "claude $*" >> "$STUBLOG"
case "$*" in
    "mcp --help") printf '  list\\n  add\\n  remove\\n  logout\\n' ;;
    "plugin --help") printf '  install\\n  uninstall\\n  marketplace\\n' ;;
    "plugin marketplace --help") printf '  add\\n  remove\\n  list\\n' ;;
    "mcp remove"*) printf '{"mcpServers": {}}\\n' > "$HOME/.claude.json" ;;
esac
exit 0
"""

_PIPEFY = """#!/bin/sh
printf '%s\\n' "pipefy $*" >> "$STUBLOG"
mkdir -p "$HOME/.config/pipefy"
: > "$HOME/.config/pipefy/refresh.lock"
exit 0
"""

_SECRET_TOOL = """#!/bin/sh
printf '%s\\n' "secret-tool $*" >> "$STUBLOG"
if [ "$1" = search ] && [ -f "$STUBSTATE/keychain" ]; then
    printf 'attribute.username = signin.pipefy.com|pipefy-cli\\n'
fi
if [ "$1" = clear ]; then
    rm -f "$STUBSTATE/keychain"
fi
exit 0
"""

_SECURITY = """#!/bin/sh
printf '%s\\n' "security $*" >> "$STUBLOG"
case "$1" in
    find-generic-password)
        [ -f "$STUBSTATE/keychain" ] || exit 44 ;;
    dump-keychain)
        [ -f "$STUBSTATE/keychain" ] || exit 0
        printf 'keychain: "login"\\n'
        printf 'class: "genp"\\n'
        printf 'attributes:\\n'
        printf '    "acct"<blob>="signin.pipefy.com|pipefy-cli"\\n'
        printf '    "svce"<blob>="pipefy"\\n' ;;
    delete-generic-password)
        rm -f "$STUBSTATE/keychain" ;;
esac
exit 0
"""


def _stub_path(
    tmp_path: Path,
    *,
    os_name: str = "Linux",
    git: bool = False,
    claude: str | None = _CLAUDE,
    pipefy: bool = True,
    ps_output: str = "",
) -> Path:
    stub = tmp_path / "stubbin"
    stub.mkdir(parents=True, exist_ok=True)
    wanted = list(_BASE_TOOLS)
    if git:
        wanted.append("git")
    for tool in wanted:
        real = shutil.which(tool)
        if real is None:  # pragma: no cover - depends on the host image
            pytest.skip(f"{tool} not available to stub")
        link = stub / tool
        if not link.exists():
            link.symlink_to(real)
    _write_exec(stub / "uname", f'#!/bin/sh\nprintf "%s\\n" "{os_name}"\n')
    _write_exec(stub / "uv", _UV)
    _write_exec(stub / "secret-tool", _SECRET_TOOL)
    _write_exec(stub / "security", _SECURITY)
    # printf interprets escapes in its format string, so ps_output carries
    # real newlines into the stub's output.
    _write_exec(stub / "ps", f"#!/bin/sh\nprintf '{ps_output}'\nexit 0\n")
    if claude is not None:
        _write_exec(stub / "claude", claude)
    if pipefy:
        _write_exec(stub / "pipefy", _PIPEFY)
    return stub


class Run:
    """A completed run plus the two traces it produced."""

    def __init__(self, proc: subprocess.CompletedProcess[str], log: Path) -> None:
        self.proc = proc
        self.returncode = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr
        self.stubs = (
            log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        )
        self.trace = [
            line[2:] for line in proc.stderr.splitlines() if line.startswith("+ ")
        ]

    def index(self, needle: str) -> int:
        """Position of the first traced command containing ``needle``."""
        for position, line in enumerate(self.trace):
            if needle in line:
                return position
        raise AssertionError(f"{needle!r} not in trace:\n" + "\n".join(self.trace))

    def missing(self, needle: str) -> bool:
        return all(needle not in line for line in self.trace)


def _run(
    home: Path,
    stub: Path,
    *,
    args: tuple[str, ...] = ("--yes",),
    cwd: Path | None = None,
    extra_path: tuple[Path, ...] = (),
    env_extra: dict[str, str] | None = None,
    script: Path | None = None,
) -> Run:
    log = stub.parent / "stub.log"
    state = stub.parent / "stubstate"
    state.mkdir(exist_ok=True)
    env = {
        "HOME": str(home),
        "PATH": ":".join([str(p) for p in extra_path] + [str(stub)]),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "UV_CACHE_DIR": str(home / "no-such-uv-cache"),
        "STUBLOG": str(log),
        "STUBSTATE": str(state),
    }
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [_SH, str(script or _SCRIPT), *args],
        cwd=str(cwd or home),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return Run(proc, log)


def _no_uv_tools(stub: Path) -> Path:
    """A `uv` that reports an empty tool directory, so a plan can be empty."""
    _write_exec(
        stub / "uv", '#!/bin/sh\nprintf \'%s\\n\' "uv $*" >> "$STUBLOG"\nexit 0\n'
    )
    return stub


def _keychain_entry(stub: Path) -> None:
    state = stub.parent / "stubstate"
    state.mkdir(exist_ok=True)
    (state / "keychain").write_text("", encoding="utf-8")


def _full_fixture(home: Path) -> None:
    """One artifact of every kind, so a run exercises the whole sequence."""
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy-dev": {"command": "uvx", "args": ["pipefy-mcp-server"]},
                "work": {"type": "http", "url": "https://mcp.pipefy.com/mcp"},
            },
            "pluginUsage": {"pipefy@pipefy": 3},
        },
    )
    _write_json(
        home / ".claude" / "settings.json",
        {
            "env": {"PIPEFY_TOKEN": "sentinel-token"},
            "extraKnownMarketplaces": {"pipefy": {}},
            "enabledPlugins": {"pipefy@pipefy": True},
        },
    )
    clone = home / ".claude" / "plugins" / "marketplaces" / "pipefy"
    clone.mkdir(parents=True)
    _write_json(
        home / ".claude" / "plugins" / "known_marketplaces.json",
        {"pipefy": {"installLocation": str(clone)}},
    )
    _write_json(
        home / ".claude" / "plugins" / "installed_plugins.json",
        {
            "version": 2,
            "plugins": {
                "pipefy@pipefy": [
                    {"scope": "user", "installPath": str(clone), "version": "0.5.0"}
                ]
            },
        },
    )
    _write_json(
        home / ".cursor" / "mcp.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text(
        '[profiles.default]\nmodel = "x"\n\n'
        '[mcp_servers.pipefy]\ncommand = "pipefy-mcp-server"\n',
        encoding="utf-8",
    )
    _install_skills(home, "pipefy-reports")


# `npx skills add` records the source of every skill it writes in a lock file.
# That record is the only provenance a skill has: the `pipefy-` prefix is a
# namespace anyone may write in, and reading it as ownership is how a teardown
# deletes work it never created.
def _install_skills(home: Path, *names: str, source: str = "pipefy/ai-toolkit") -> None:
    lock_path = home / ".agents" / ".skill-lock.json"
    lock = (
        json.loads(lock_path.read_text(encoding="utf-8"))
        if lock_path.exists()
        else {"version": 3, "skills": {}}
    )
    for name in names:
        directory = home / ".claude" / "skills" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        lock["skills"][name] = {
            "installedAt": "2026-01-01T00:00:00.000Z",
            "skillPath": f"skills/{name}/SKILL.md",
            "source": source,
            "sourceType": "github",
            "sourceUrl": f"https://github.com/{source}.git",
        }
    _write_json(lock_path, lock)


# The other layout, and the one a `curl | sh` install from inside a project
# gets: `skills add` writes the lock at the base rather than inside the agent
# directory, and links a skills directory beside it at the content under
# `<base>/.agents/skills`. Both were observed; only the lock's name and place
# differ, which is why the store is derived from the base.
def _install_project_skills(
    base: Path, *names: str, source: str = "pipefy/ai-toolkit"
) -> Path:
    lock_path = base / "skills-lock.json"
    lock = (
        json.loads(lock_path.read_text(encoding="utf-8"))
        if lock_path.exists()
        else {"version": 3, "skills": {}}
    )
    for name in names:
        store = base / ".agents" / "skills" / name
        store.mkdir(parents=True, exist_ok=True)
        (store / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        link = base / ".claude" / "skills" / name
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(store)
        lock["skills"][name] = {
            "installedAt": "2026-01-01T00:00:00.000Z",
            "skillPath": f"skills/{name}/SKILL.md",
            "source": source,
            "sourceType": "github",
            "sourceUrl": f"https://github.com/{source}.git",
        }
    _write_json(lock_path, lock)
    return lock_path


# ------------------------------------------------------------ the sequence


def test_the_command_sequence_is_credentials_configs_tools_skills_state(tmp_path):
    """Ordering is load-bearing and only the trace can show it."""
    home = _home(tmp_path)
    _full_fixture(home)
    stub = _stub_path(tmp_path)
    _keychain_entry(stub)

    run = _run(home, stub)

    revoke = run.index("pipefy auth logout")
    hosted = run.index("claude mcp logout work")
    keychain = run.index("secret-tool clear")
    registration = run.index("claude mcp remove pipefy-dev")
    cursor = run.index("mcpServers pipefy from")
    tool = run.index("uv tool uninstall pipefy-cli")
    skill = run.index("skills/pipefy-reports")
    lock = run.index("refresh.lock")

    # Only `pipefy auth logout` revokes server-side, and that ability goes away
    # with the tool environment, so it leads.
    assert revoke < keychain
    assert revoke < hosted
    # Credentials before client configs before tools: the reverse strands a
    # registration pointing at a binary that no longer exists.
    assert keychain < registration
    assert registration < tool
    assert cursor < tool
    assert tool < skill
    # Runtime state last, because logout recreates the config directory.
    assert skill < lock


def test_logout_recreates_the_config_directory_and_the_ordering_still_clears_it(
    tmp_path,
):
    """`pipefy auth logout` recreates ~/.config/pipefy with a refresh.lock."""
    home = _home(tmp_path)
    stub = _stub_path(tmp_path)
    _keychain_entry(stub)
    config = home / ".config" / "pipefy"
    assert not config.exists()

    run = _run(home, stub)

    assert "pipefy auth logout" in run.stubs
    assert run.index("pipefy auth logout") < run.index("refresh.lock")
    # The directory the logout brought back is gone again at the end.
    assert not config.exists(), sorted(p.name for p in config.iterdir())


def test_uv_cache_clean_is_never_invoked(tmp_path):
    home = _home(tmp_path)
    _full_fixture(home)
    stub = _stub_path(tmp_path)
    _keychain_entry(stub)

    run = _run(home, stub)

    assert any(line.startswith("uv tool uninstall") for line in run.stubs)
    for line in run.stubs:
        assert "cache clean" not in line
        assert "cache prune" not in line
    assert run.missing("cache clean")


def test_registrations_are_removed_under_the_name_they_were_registered_with(tmp_path):
    """A real environment had the server registered as `pipefy-dev`."""
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy-dev": {"command": "uvx", "args": ["pipefy-mcp-server"]}
            }
        },
    )

    run = _run(home, _stub_path(tmp_path))

    assert "claude mcp remove pipefy-dev -s user" in run.stubs
    assert not any(line == "claude mcp remove pipefy -s user" for line in run.stubs)


def test_cli_delegation_is_gated_on_a_verb_probe_not_a_version(tmp_path):
    """With no `logout` verb, the run falls back to the in-client instruction."""
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy": {"type": "http", "url": "https://mcp.pipefy.com/mcp"}
            }
        },
    )
    older = _CLAUDE.replace("\\n  logout", "")
    assert "logout" not in older
    stub = _stub_path(tmp_path, claude=older)

    run = _run(home, stub)

    assert "claude mcp --help" in run.stubs
    assert not any(line.startswith("claude mcp logout") for line in run.stubs)
    assert "Clear authentication" in run.stdout
    # The registration itself still goes, through the verb that does exist.
    assert "claude mcp remove pipefy -s user" in run.stubs


def test_without_the_client_cli_the_config_is_edited_directly(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )
    stub = _stub_path(tmp_path, claude=None)

    run = _run(home, stub)

    payload = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    assert payload["mcpServers"] == {}
    assert any(p.name.startswith(".claude.json.bak.") for p in home.iterdir())
    # There was no client CLI to delegate to, so none was probed or called.
    assert not any(line.startswith("claude") for line in run.stubs)


# ------------------------------------------------------------- codex adapter


def _codex(home: Path, body: str) -> Path:
    path = home / ".codex" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_an_installer_appended_codex_section_is_excised(tmp_path):
    home = _home(tmp_path)
    codex = _codex(
        home,
        '[profiles.default]\nmodel = "x"\n\n'
        '[mcp_servers.pipefy]\ncommand = "pipefy-mcp-server"\n\n'
        '[history]\npersistence = "none"\n',
    )

    run = _run(home, _stub_path(tmp_path))

    body = codex.read_text(encoding="utf-8")
    assert "[mcp_servers.pipefy]" not in body
    # Everything either side survives, separator and all.
    assert body == (
        '[profiles.default]\nmodel = "x"\n\n[history]\npersistence = "none"\n'
    )
    assert (codex.parent / f"{codex.name}.bak.{_stamp(run)}").exists()


def test_a_hand_edited_codex_section_degrades_to_report_only(tmp_path):
    home = _home(tmp_path)
    codex = _codex(
        home,
        '[mcp_servers.pipefy]\ncommand = "pipefy-mcp-server"\n'
        'args = ["--profile", "mine"]\n\n'
        '[mcp_servers.pipefy.env]\nPIPEFY_MCP_PROFILE = "admin"\n',
    )
    before = codex.read_text(encoding="utf-8")

    run = _run(home, _stub_path(tmp_path))

    assert codex.read_text(encoding="utf-8") == before
    assert "holds more than the single line the installer appends" in run.stdout
    assert "excise the section and any sub-table of it yourself" in run.stdout


def test_a_codex_section_that_ends_the_file_takes_its_blank_line_with_it(tmp_path):
    home = _home(tmp_path)
    codex = _codex(
        home,
        '[profiles.default]\nmodel = "x"\n\n'
        '[mcp_servers.pipefy]\ncommand = "pipefy-mcp-server"\n',
    )

    _run(home, _stub_path(tmp_path))

    assert codex.read_text(encoding="utf-8") == '[profiles.default]\nmodel = "x"\n'


# --------------------------------------------------------- the delete guard


def _guard_run(tmp_path, snippet: str, home: Path) -> subprocess.CompletedProcess[str]:
    """Source the script with its entry point removed, then call into it.

    DRY_RUN is forced on so that a guard which failed to refuse would print the
    command rather than run it. The assertions then distinguish the two.
    """
    body = _SCRIPT.read_text(encoding="utf-8")
    assert body.endswith('main "$@"\n')
    lib = tmp_path / "lib.sh"
    lib.write_text(body[: -len('main "$@"\n')] + "DRY_RUN=1\n" + snippet, "utf-8")
    return subprocess.run(
        [_SH, str(lib)],
        env={"HOME": str(home), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ('remove_path ""', "refusing to remove an empty path"),
        ("remove_path", "refusing to remove an empty path"),
        ('remove_path "/"', "refusing to remove /"),
        ('remove_path "//"', "refusing to remove /"),
        ('remove_path "$HOME"', "refusing to remove $HOME"),
        ('remove_path "$HOME/"', "refusing to remove $HOME"),
        ('remove_path "relative/path"', "refusing to remove a relative path"),
        ('remove_path "$HOME" empty-dir', "refusing to remove $HOME"),
        # Traversal: an absolute path is not a resolved one, and a guard that
        # compares text lets `..` walk straight past both refusals.
        ('remove_path "$HOME/."', "refusing to remove $HOME"),
        ('remove_path "$HOME/.."', "it contains $HOME"),
        ('remove_path "$HOME/x/../.."', "it contains $HOME"),
        ('remove_path "$HOME/../.." empty-dir', "it contains $HOME"),
        ('remove_path "/tmp/../.."', "refusing to remove /"),
    ],
)
def test_the_deletion_guard_refuses(tmp_path, snippet, message):
    home = _home(tmp_path)
    result = _guard_run(tmp_path, snippet + "\n", home)
    assert result.returncode == 2, result.stdout + result.stderr
    assert message in result.stderr
    # Not even the dry-run echo: the guard refuses before anything is traced.
    assert "+ rm" not in result.stderr
    assert "+ rmdir" not in result.stderr


def test_the_deletion_guard_allows_a_path_below_home(tmp_path):
    home = _home(tmp_path)
    result = _guard_run(tmp_path, 'touch "$HOME/x"\nremove_path "$HOME/x"\n', home)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"+ rm -rf -- {home}/x" in result.stderr


def test_the_deletion_guard_does_not_follow_a_symlink_out(tmp_path):
    """What is removed is the link, so the link's own path is what is judged."""
    home = _home(tmp_path)
    (home / "link").symlink_to(home.parent)
    result = _guard_run(tmp_path, 'remove_path "$HOME/link"\n', home)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"+ rm -rf -- {home}/link" in result.stderr


# ------------------------------------------------------- marketplace clone


def test_a_marketplace_clone_outside_the_plugin_tree_is_never_deleted(tmp_path):
    """`installLocation` is data this script did not write. It is a claim."""
    home = _home(tmp_path)
    canary = tmp_path / "canary"
    canary.mkdir()
    (canary / "keep.txt").write_text("mine\n", encoding="utf-8")
    _write_json(
        home / ".claude" / "plugins" / "known_marketplaces.json",
        {"pipefy": {"installLocation": str(canary)}},
    )
    # No client CLI, so teardown falls back to editing the registry itself —
    # the path on which the recorded location becomes a deletion target.
    stub = _stub_path(tmp_path, claude=None)

    run = _run(home, stub)

    assert canary.is_dir() and (canary / "keep.txt").exists()
    assert "which is outside" in run.stdout
    assert run.missing(f"rm -rf -- {canary}")
    registry = json.loads(
        (home / ".claude" / "plugins" / "known_marketplaces.json").read_text()
    )
    assert "pipefy" not in registry


def test_the_canonical_marketplace_clone_is_deleted_and_disclosed(tmp_path):
    home = _home(tmp_path)
    clone = home / ".claude" / "plugins" / "marketplaces" / "pipefy"
    clone.mkdir(parents=True)
    (clone / "marketplace.json").write_text("{}", encoding="utf-8")
    _write_json(
        home / ".claude" / "plugins" / "known_marketplaces.json",
        {"pipefy": {"installLocation": str(clone)}},
    )

    run = _run(home, _stub_path(tmp_path, claude=None))

    assert f"delete its clone at {clone}" in run.stdout
    assert not clone.exists()


# ----------------------------------------------------- codex sub-tables


def test_a_codex_env_subtable_keeps_the_whole_section_report_only(tmp_path):
    """A sibling `[mcp_servers.<name>.env]` is invisible to a scan that stops
    at the next `[`, so excising the parent would strand its secrets."""
    home = _home(tmp_path)
    codex = _codex(
        home,
        '[mcp_servers.pipefy]\ncommand = "pipefy-mcp-server"\n\n'
        '[mcp_servers.pipefy.env]\nPIPEFY_TOKEN = "sentinel-token"\n',
    )
    before = codex.read_text(encoding="utf-8")

    run = _run(home, _stub_path(tmp_path))

    assert codex.read_text(encoding="utf-8") == before
    assert "sub-table" in run.stdout
    assert "sentinel-token" not in run.stdout
    # A run that leaves credential material behind cannot report success.
    assert run.returncode != 0


# ---------------------------------------------------------- JSON rewrites


def test_a_registration_removal_leaves_utf8_siblings_literal(tmp_path):
    home = _home(tmp_path)
    config = home / ".cursor" / "mcp.json"
    _write_json(
        config,
        {
            "mcpServers": {
                "pipefy": {"command": "pipefy-mcp-server"},
                "café": {"command": "other", "args": ["--naïve", "ção"]},
            }
        },
    )

    _run(home, _stub_path(tmp_path))

    raw = config.read_text(encoding="utf-8")
    assert "café" in raw and "naïve" in raw
    assert "\\u" not in raw
    assert json.loads(raw)["mcpServers"] == {
        "café": {"command": "other", "args": ["--naïve", "ção"]}
    }


# ----------------------------------------------------------- the exit contract


def test_an_empty_plan_with_findings_left_does_not_read_as_clean(tmp_path):
    """`--scan` exits 1 on this tree; a teardown that removed nothing must too."""
    home = _home(tmp_path)
    _codex(
        home,
        '[mcp_servers.pipefy]\ncommand = "pipefy-mcp-server"\n'
        'args = ["--profile", "mine"]\n',
    )
    stub = _no_uv_tools(_stub_path(tmp_path))

    scan = _run(home, stub, args=("--scan",))
    run = _run(home, stub)

    assert scan.returncode == 1
    assert "Nothing to remove." in run.stdout
    assert run.returncode == scan.returncode
    # The notes that explain why nothing was planned are printed, not swallowed
    # with the teardown report this path skips.
    assert "Left alone:" in run.stdout
    assert "excise the section and any sub-table of it yourself" in run.stdout


def test_an_empty_plan_on_a_clean_machine_still_exits_zero(tmp_path):
    stub = _no_uv_tools(_stub_path(tmp_path, pipefy=False))

    run = _run(_home(tmp_path), stub)
    assert "Nothing to remove." in run.stdout
    assert run.returncode == 0, run.stdout


# ------------------------------------------------------------------- skills


def test_a_skill_the_toolkit_did_not_install_survives_teardown(tmp_path):
    """The `pipefy-` prefix is a namespace, not a claim of ownership."""
    home = _home(tmp_path)
    _install_skills(home, "pipefy-reports")
    mine = home / ".claude" / "skills" / "pipefy-tasks"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("---\nname: mine\n---\n", encoding="utf-8")

    run = _run(home, _stub_path(tmp_path))

    assert (mine / "SKILL.md").read_text(encoding="utf-8") == "---\nname: mine\n---\n"
    assert "nothing records where it came from" in run.stdout
    assert not (home / ".claude" / "skills" / "pipefy-reports").exists()
    assert run.missing("skills/pipefy-tasks")


def test_a_skill_from_another_repository_survives_teardown(tmp_path):
    home = _home(tmp_path)
    _install_skills(home, "pipefy-tasks", source="someone-else/their-skills")

    run = _run(home, _stub_path(tmp_path))

    assert (home / ".claude" / "skills" / "pipefy-tasks").is_dir()
    assert "not this toolkit" in run.stdout


def test_a_skill_linked_into_a_shared_store_takes_its_content_with_it(tmp_path):
    """`skills add` writes a store and links agents at it; the link is not the
    skill, and removing only the link leaves the content and the lock entry."""
    home = _home(tmp_path)
    _install_skills(home, "pipefy-reports")
    lock = home / ".agents" / ".skill-lock.json"
    store = home / ".agents" / "skills" / "pipefy-reports"
    store.mkdir(parents=True)
    (store / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    link = home / ".claude" / "skills" / "pipefy-reports"
    shutil.rmtree(link)
    link.symlink_to(store)

    run = _run(home, _stub_path(tmp_path))

    assert not link.exists() and not link.is_symlink()
    assert not store.exists()
    # The entry goes, and with nothing else recorded in it the lock goes too.
    assert f"drop the pipefy-reports entry from {lock}" in run.stdout
    assert not lock.exists()
    assert "content at" in run.stdout


def test_a_skill_linked_outside_the_store_keeps_its_content(tmp_path):
    """Following a link is unbounded reach, so the target is confined.

    The parallel of the marketplace `installLocation` case: the link goes, the
    directory it pointed at does not, and the report says which.
    """
    home = _home(tmp_path)
    _install_skills(home, "pipefy-reports")
    canary = tmp_path / "canary"
    canary.mkdir()
    (canary / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    (canary / "keep.txt").write_text("mine\n", encoding="utf-8")
    link = home / ".claude" / "skills" / "pipefy-reports"
    shutil.rmtree(link)
    link.symlink_to(canary)

    run = _run(home, _stub_path(tmp_path))

    assert canary.is_dir() and (canary / "keep.txt").exists()
    assert run.missing(f"rm -rf -- {canary}")
    # The link itself is still this toolkit's and still goes.
    assert not link.is_symlink() and not link.exists()
    assert "outside the skills store" in run.stdout
    assert str(canary) in run.stdout
    assert "left exactly as it is" in run.stdout


def test_a_skill_link_with_no_lock_file_to_derive_a_store_from_keeps_its_content(
    tmp_path,
):
    """No lock file in either layout, no derived store, no permitted target."""
    home = _home(tmp_path)
    store = home / ".agents" / "skills" / "pipefy-reports"
    store.mkdir(parents=True)
    (store / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    link = home / ".claude" / "skills" / "pipefy-reports"
    link.parent.mkdir(parents=True)
    link.symlink_to(store)
    # The receipt says the installer added it, so provenance passes; nothing
    # says where the content legitimately lives.
    receipt = home / ".local" / "state" / "pipefy" / "install-receipt"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        "record=begin\nschema=1\nskill=pipefy-reports\nrecord=end\n", encoding="utf-8"
    )

    run = _run(home, _stub_path(tmp_path))

    assert store.is_dir()
    assert not link.is_symlink()
    assert "outside the skills store" in run.stdout


def test_a_project_install_takes_its_store_and_its_lock_file(tmp_path):
    """The layout a round trip run from a project directory produces.

    The lock is at the base and the store is under `.agents` beside it, so a
    store derived from the lock's own directory points at nothing and the
    content survives a teardown that reported success.
    """
    home = _home(tmp_path)
    base = tmp_path / "roundtrip"
    base.mkdir()
    lock = _install_project_skills(base, "pipefy-reports", "pipefy-relations")
    links = base / ".claude" / "skills"
    store = base / ".agents" / "skills"

    run = _run(home, _stub_path(tmp_path), cwd=base)

    assert sorted(p.name for p in links.iterdir()) == []
    # The content, not the empty directory it sat in: the round-trip snapshot
    # this mirrors compares files, and an empty `.agents/skills` is not state.
    assert sorted(p.name for p in store.iterdir()) == []
    assert list(base.rglob("SKILL.md")) == []
    assert not lock.exists()
    assert "2 pipefy-* skills from this toolkit" in run.stdout


def test_a_project_lock_still_holding_another_source_is_kept(tmp_path):
    """The lock is `skills add`'s file, not this toolkit's."""
    home = _home(tmp_path)
    base = tmp_path / "roundtrip"
    base.mkdir()
    lock = _install_project_skills(base, "pipefy-reports")
    _install_project_skills(base, "pipefy-theirs", source="someone-else/theirs")

    run = _run(home, _stub_path(tmp_path), cwd=base)

    assert lock.exists()
    assert list(json.loads(lock.read_text(encoding="utf-8"))["skills"]) == [
        "pipefy-theirs"
    ]
    assert (base / ".agents" / "skills" / "pipefy-theirs").is_dir()
    assert not (base / ".agents" / "skills" / "pipefy-reports").exists()
    assert "still records skills from another source" in run.stdout


def test_both_layouts_at_once_each_answer_from_their_own_lock(tmp_path):
    """The same skill name is in both locks, and each has its own store.

    Keyed on the name alone, the first record found answers for both: a project
    skill is judged against the global store, read as outside it, and left —
    reported as left alone, exit 0, nothing removed.
    """
    home = _home(tmp_path)
    base = tmp_path / "roundtrip"
    base.mkdir()
    # Global: lock in the agent directory, links from ~/.claude/skills.
    _install_skills(home, "pipefy-reports")
    global_lock = home / ".agents" / ".skill-lock.json"
    global_store = home / ".agents" / "skills" / "pipefy-reports"
    global_store.mkdir(parents=True)
    (global_store / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    global_link = home / ".claude" / "skills" / "pipefy-reports"
    shutil.rmtree(global_link)
    global_link.symlink_to(global_store)
    # Project: same skill name, its own lock, its own store.
    project_lock = _install_project_skills(base, "pipefy-reports")
    project_store = base / ".agents" / "skills" / "pipefy-reports"

    run = _run(home, _stub_path(tmp_path), cwd=base)

    # Each half judged against its own record, and both go.
    assert not project_store.exists(), run.stdout
    assert not project_lock.exists()
    assert not (base / ".claude" / "skills" / "pipefy-reports").is_symlink()
    assert not global_store.exists()
    assert not global_lock.exists()
    assert not global_link.is_symlink()
    assert "outside the skills store" not in run.stdout


# ------------------------------------------------------------- hosted token


def test_the_hosted_logout_runs_after_the_shadowing_entry_and_before_its_own(
    tmp_path,
):
    """`mcp logout` resolves a name across scopes and takes no scope flag.

    Run while a higher-precedence entry of the same name is still registered,
    it binds to that one and the hosted token is never cleared.
    """
    home = _home(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_json(
        repo / ".mcp.json",
        {"mcpServers": {"pipefy": {"command": "uvx", "args": ["pipefy-mcp-server"]}}},
    )
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy": {"type": "http", "url": "https://mcp.pipefy.com/mcp"}
            }
        },
    )

    run = _run(home, _stub_path(tmp_path, git=True), cwd=repo)

    project = run.index("mcpServers pipefy from")
    logout = run.index("claude mcp logout pipefy")
    user = run.index("claude mcp remove pipefy -s user")
    assert project < logout < user


def test_a_hosted_logout_that_exits_zero_is_not_reported_as_a_removal(tmp_path):
    """The client's OAuth store is opaque here, so exit 0 is not proof.

    A stub that logs the call and does nothing is indistinguishable from one
    that cleared the token, and the re-scan cannot tell them apart either.
    """
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy": {"type": "http", "url": "https://mcp.pipefy.com/mcp"}
            }
        },
    )
    stub = _no_uv_tools(_stub_path(tmp_path, pipefy=False, claude=_CLAUDE_THAT_REMOVES))

    run = _run(home, stub)

    assert "claude mcp logout pipefy" in run.stubs
    # Everything the re-scan can check came back clean, so the token is the only
    # thing left in question — and it is the one thing nothing can check.
    assert "no registration in any JSON client config runs this toolkit" in run.stdout
    assert "Asked for, result not observable from here:" in run.stdout
    assert "1 unverifiable" in run.stdout
    assert "it is not proof" in run.stdout
    removed = run.stdout.split("Removed:", 1)[1].split("\n\n", 1)[0]
    assert "OAuth" not in removed, removed
    # No "deleted but not revoked" story either: nothing was observed deleted.
    assert "A credential was deleted from this machine" not in run.stdout
    # And a clean re-scan plus an unverifiable clear is not full success.
    assert run.returncode == 1, run.stdout


def test_a_failing_hosted_logout_is_reported_rather_than_counted_as_done(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy": {"type": "http", "url": "https://mcp.pipefy.com/mcp"}
            }
        },
    )
    failing = _CLAUDE.replace(
        "exit 0\n",
        'case "$*" in "mcp logout"*) exit 1 ;; esac\nexit 0\n',
        1,
    )
    stub = _stub_path(tmp_path, claude=failing)

    run = _run(home, stub)

    assert "claude mcp logout pipefy" in run.stubs
    assert "Failed — these are still here:" in run.stdout
    assert "clear the stored OAuth token for 'pipefy'" in run.stdout
    assert "Clear authentication" in run.stdout
    assert run.returncode == 2


# ----------------------------------------------------------------- approval


def _stamp(run: Run) -> str:
    match = re.search(r"\.bak\.(\d{14})", run.stdout + run.stderr)
    assert match, "no timestamped backup in the report"
    return match.group(1)


def test_yes_approves_every_tier(tmp_path):
    home = _home(tmp_path)
    _full_fixture(home)
    stub = _stub_path(tmp_path)
    _keychain_entry(stub)
    (home / ".zshrc").write_text(
        'export PIPEFY_TOKEN="x"\nexport PIPEFY_ORG_ID=1\n', encoding="utf-8"
    )

    run = _run(home, stub)

    assert "[1] Ours, reversible" in run.stdout
    assert "[2] Credentials" in run.stdout and "cannot be undone" in run.stdout
    assert "[3] Your files" in run.stdout and "backed up first" in run.stdout
    assert "declined" not in run.stdout
    # One action from each tier actually happened.
    assert "uv tool uninstall pipefy-cli" in run.stubs
    assert "secret-tool clear service pipefy username signin.pipefy.com|pipefy-cli" in (
        run.stubs
    )
    assert (home / ".zshrc").read_text(encoding="utf-8") == ""


def test_no_tty_without_yes_refuses_to_guess(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".cursor" / "mcp.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )

    run = _run(home, _stub_path(tmp_path), args=())

    # No TTY at all errors out; a TTY that answers nothing declines every tier.
    # Either way the plan is printed first and nothing is removed.
    assert run.returncode in (1, 2)
    assert "PLAN — " in run.stdout
    assert (
        "No TTY available for prompt" in run.stderr
        or "Nothing was removed." in run.stdout
    )
    assert json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"]
    assert run.trace == []


def test_keep_credentials_skips_tier_two_only(tmp_path):
    home = _home(tmp_path)
    _full_fixture(home)
    stub = _stub_path(tmp_path)
    _keychain_entry(stub)

    run = _run(home, stub, args=("--yes", "--keep-credentials"))

    assert "[2] Credentials" not in run.stdout
    assert "kept by --keep-credentials" in run.stdout
    assert not any(line.startswith("pipefy auth logout") for line in run.stubs)
    assert not any(line.startswith("secret-tool clear") for line in run.stubs)
    # Tier 1 still ran.
    assert "uv tool uninstall pipefy-cli" in run.stubs


def test_keep_config_keeps_user_authored_configuration(tmp_path):
    home = _home(tmp_path)
    _full_fixture(home)
    config = home / ".config" / "pipefy"
    config.mkdir(parents=True)
    (config / "config.toml").write_text("org_id = 1\n", encoding="utf-8")
    (config / ".env").write_text("PIPEFY_ORG_ID=1\n", encoding="utf-8")
    (config / "refresh.lock").write_text("", encoding="utf-8")
    (home / ".zshrc").write_text("export PIPEFY_ORG_ID=1\n", encoding="utf-8")

    run = _run(home, _stub_path(tmp_path), args=("--yes", "--keep-config"))

    assert "kept by --keep-config" in run.stdout
    assert (config / "config.toml").exists()
    assert (config / ".env").exists()
    assert (home / ".zshrc").read_text(encoding="utf-8") == "export PIPEFY_ORG_ID=1\n"
    # Ours in the same directory still goes.
    assert not (config / "refresh.lock").exists()


def test_config_toml_and_env_need_consent_and_are_backed_up(tmp_path):
    home = _home(tmp_path)
    config = home / ".config" / "pipefy"
    config.mkdir(parents=True)
    (config / "config.toml").write_text("org_id = 1\n", encoding="utf-8")
    (config / ".env").write_text("PIPEFY_ORG_ID=1\n", encoding="utf-8")

    run = _run(home, _stub_path(tmp_path))

    assert "[3] Your files" in run.stdout
    assert "delete your" in run.stdout
    stamp = _stamp(run)
    assert (config / f"config.toml.bak.{stamp}").exists()
    assert (config / f".env.bak.{stamp}").exists()
    assert not (config / "config.toml").exists()
    # A backup of the user's own file keeps the directory alive, and the report
    # says which file did it.
    assert "was kept: it still holds" in run.stdout


def test_backups_carry_a_timestamped_suffix_and_the_original_bytes(tmp_path):
    home = _home(tmp_path)
    before = {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}}
    _write_json(home / ".cursor" / "mcp.json", before)

    run = _run(home, _stub_path(tmp_path))

    stamp = _stamp(run)
    backup = home / ".cursor" / f"mcp.json.bak.{stamp}"
    assert re.fullmatch(r"\d{14}", stamp)
    assert json.loads(backup.read_text(encoding="utf-8")) == before
    assert json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"] == {}


# ------------------------------------------------------- guards and refusals


def test_the_live_server_guard_names_the_running_client(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".cursor" / "mcp.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )
    stub = _stub_path(tmp_path, ps_output="/usr/bin/login\\n/Applications/Cursor\\n")

    run = _run(home, stub)

    assert "Running client detected: Cursor" in run.stdout
    assert "can put back an entry this" in run.stdout
    # --yes proceeds, but the report says the run happened under a live client.
    assert "may have rewritten their config" in run.stdout


def test_an_unrelated_process_does_not_trip_the_live_server_guard(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".cursor" / "mcp.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )
    stub = _stub_path(tmp_path, ps_output="/usr/bin/claudette\\n/bin/cursorish\\n")

    run = _run(home, stub)

    assert "Running client detected" not in run.stdout


def test_a_git_tracked_project_file_is_disabled_rather_than_edited(tmp_path):
    home = _home(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    tracked = {
        "mcpServers": {"pipefy": {"command": "uvx", "args": ["pipefy-mcp-server"]}}
    }
    _write_json(repo / ".mcp.json", tracked)
    stub = _stub_path(tmp_path, git=True)
    git = str(stub / "git")
    subprocess.run([git, "init", "-q", str(repo)], check=True)
    subprocess.run([git, "-C", str(repo), "add", ".mcp.json"], check=True)

    run = _run(home, stub, cwd=repo)

    assert json.loads((repo / ".mcp.json").read_text(encoding="utf-8")) == tracked
    assert "through disabledMcpjsonServers" in run.stdout
    payload = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    assert payload["projects"][str(repo)]["disabledMcpjsonServers"] == ["pipefy"]


def test_dry_run_prints_the_plan_and_changes_nothing(tmp_path):
    home = _home(tmp_path)
    _full_fixture(home)
    stub = _stub_path(tmp_path)
    _keychain_entry(stub)
    before = {
        str(path.relative_to(home)): path.read_bytes()
        for path in home.rglob("*")
        if path.is_file()
    }

    run = _run(home, stub, args=("--dry-run",))

    assert run.returncode == 0
    assert "PLAN — " in run.stdout
    assert "--dry-run: nothing was changed." in run.stdout
    after = {
        str(path.relative_to(home)): path.read_bytes()
        for path in home.rglob("*")
        if path.is_file()
    }
    assert after == before
    # Only the read-only probes the scan itself makes.
    for line in run.stubs:
        assert line in ("uv tool list", "secret-tool search service pipefy"), line


def test_scan_writes_nothing_even_with_state_everywhere(tmp_path):
    home = _home(tmp_path)
    _full_fixture(home)
    stub = _stub_path(tmp_path)
    _keychain_entry(stub)
    before = {
        str(path.relative_to(home)): path.read_bytes()
        for path in home.rglob("*")
        if path.is_file()
    }

    run = _run(home, stub, args=("--scan",))

    assert run.returncode == 1
    after = {
        str(path.relative_to(home)): path.read_bytes()
        for path in home.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert run.trace == []
    assert "--scan removes nothing" in run.stdout


def test_a_deleted_credential_that_could_not_be_revoked_says_so(tmp_path):
    home = _home(tmp_path)
    stub = _stub_path(tmp_path, pipefy=False)
    _keychain_entry(stub)

    run = _run(home, stub)

    assert "could not be revoked at the identity provider" in run.stdout
    assert "stays valid" in run.stdout
    assert "secret-tool clear service pipefy username signin.pipefy.com|pipefy-cli" in (
        run.stubs
    )


def test_secrets_never_reach_the_output_of_a_teardown(tmp_path):
    sentinel = "s3cr3t-value-do-not-print"
    home = _home(tmp_path)
    _write_json(home / ".claude" / "settings.json", {"env": {"PIPEFY_TOKEN": sentinel}})
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy": {
                    "command": "pipefy-mcp-server",
                    "env": {"PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET": sentinel},
                }
            }
        },
    )
    (home / ".zshrc").write_text(
        f'export PIPEFY_TOKEN="{sentinel}"\n', encoding="utf-8"
    )
    config = home / ".config" / "pipefy"
    config.mkdir(parents=True)
    (config / "keyring.cfg").write_text(
        f"[pipefy]\nsignin_2epipefy_2ecom_7cpipefy_2dcli = \n\t{sentinel}\n",
        encoding="utf-8",
    )

    run = _run(
        home,
        _stub_path(tmp_path),
        env_extra={"PIPEFY_TOKEN": sentinel, "PIPEFY_ORG_ID": "9876543210987"},
    )

    assert sentinel not in run.stdout
    assert sentinel not in run.stderr
    assert "9876543210987" not in run.stdout
    assert "unset PIPEFY_TOKEN" in run.stdout
    # The backup holds the secret, as a backup must; only the report is clean.
    backup = next(p for p in (home / ".claude").iterdir() if ".bak." in p.name)
    assert sentinel in backup.read_text(encoding="utf-8")


# --------------------------------------------------------- the client table


def _table_rows() -> list[list[str]]:
    body = _SCRIPT.read_text(encoding="utf-8")
    match = re.search(r'^CLIENT_TABLE="(.*?)"$', body, re.S | re.M)
    assert match, "CLIENT_TABLE not found"
    return [line.split("|") for line in match.group(1).splitlines() if line.strip()]


def _script_with_extra_client(tmp_path: Path, row: str) -> Path:
    """The shipped script plus one row, and nothing else changed."""
    body = _SCRIPT.read_text(encoding="utf-8")
    match = re.search(r'^CLIENT_TABLE="(.*?)"$', body, re.S | re.M)
    assert match
    patched = f'CLIENT_TABLE="{match.group(1)}\n{row}"'
    path = tmp_path / "uninstall-with-extra-client.sh"
    path.write_text(body[: match.start()] + patched + body[match.end() :], "utf-8")
    return path


def test_every_row_has_the_same_shape():
    rows = _table_rows()
    assert rows
    for row in rows:
        assert len(row) == 9, row
        assert row[2] in {"json", "toml"}, row
        assert row[1] == "*" or row[1] in {"Darwin", "Linux"}, row
        for capability in row[7].split(","):
            assert capability in {
                "-",
                "scopes",
                "plugin-system",
                "removal-cli",
                "typed-remote",
            }, row


def test_the_client_allowlist_in_help_comes_from_the_table(tmp_path):
    run = _run(_home(tmp_path), _stub_path(tmp_path), args=("--help",))
    assert run.returncode == 0
    listed = re.search(r"One of: (\S+)\.", run.stdout)
    assert listed
    # Every row and nothing else. `none` is install.sh's word and is refused
    # here, so advertising it would be help text that disagrees with behaviour.
    assert listed.group(1).split("|") == [row[0] for row in _table_rows()]


def test_an_unknown_client_is_rejected_against_the_table(tmp_path):
    run = _run(_home(tmp_path), _stub_path(tmp_path), args=("--client", "windsurf"))
    assert run.returncode == 2
    assert "Invalid --client: windsurf" in run.stderr


def test_a_new_client_costs_one_row_and_no_new_logic(tmp_path):
    """Detection and removal both pick up a client added as a table row."""
    home = _home(tmp_path)
    config = home / ".demo" / "mcp.json"
    _write_json(config, {"mcpServers": {"anything": {"command": "pipefy-mcp-server"}}})
    script = _script_with_extra_client(
        tmp_path, "demo|*|json|~/.demo/mcp.json|mcpServers|client:demo|-|-|-"
    )
    stub = _stub_path(tmp_path)

    scan = _run(home, stub, args=("--scan",), script=script)
    assert "client:demo scope, named 'anything': stdio" in scan.stdout

    teardown = _run(home, stub, script=script)
    assert f"remove the 'anything' registration from {config}" in teardown.stdout
    assert json.loads(config.read_text(encoding="utf-8"))["mcpServers"] == {}
    assert any(p.name.startswith("mcp.json.bak.") for p in config.parent.iterdir())

    fresh = tmp_path / "second"
    fresh.mkdir()
    _write_json(
        fresh / ".demo" / "mcp.json",
        {"mcpServers": {"anything": {"command": "pipefy-mcp-server"}}},
    )
    narrowed = _run(fresh, stub, args=("--yes", "--client", "cursor"), script=script)
    assert "--client cursor excludes demo" in narrowed.stdout
    assert json.loads((fresh / ".demo" / "mcp.json").read_text())["mcpServers"]


# ------------------------------------------------------------ source guards


def test_removal_verbs_live_only_in_the_one_guarded_primitive():
    """`--scan` safety is behavioural now, but the guard is still structural."""
    body = _SCRIPT.read_text(encoding="utf-8")
    lines = body.splitlines()
    deleting = [
        line
        for line in lines
        if re.search(r"(^|[;&|(']\s*|\brun\s+)(rm|rmdir)\s", line)
        and not line.lstrip().startswith(("#", "say ", "detail "))
    ]
    assert deleting == [
        '        run rmdir "$_rp"',
        '        run rm -rf -- "$_rp"',
        """    trap 'rm -f "$RECORDS" "$PLAN" "$NOTES"' EXIT INT TERM""",
    ], deleting


def test_uv_cache_clean_appears_only_as_advice_never_as_a_command():
    body = _SCRIPT.read_text(encoding="utf-8")
    for line in body.splitlines():
        if "cache clean" not in line:
            continue
        assert line.lstrip().startswith(("#", "say ", "detail ")), line


def test_every_planned_action_carries_a_full_row():
    """A short plan_add loses its description to `set -u` at runtime."""
    body = _SCRIPT.read_text(encoding="utf-8").replace("\\\n", " ")
    calls = [m.group(0).strip() for m in re.finditer(r"^\s*plan_add .*$", body, re.M)]
    assert calls
    for call in calls:
        flat = call.rstrip(" ;")
        # Collapse command substitutions so their inner quoting does not look
        # like another argument.
        while "$(" in flat:
            flat, changed = re.subn(r"\$\([^()]*\)", "X", flat)
            if not changed:
                break
        fields = re.findall(r"'[^']*'|\"[^\"]*\"|\S+", flat)
        assert len(fields) - 1 == 11, call


# -------------------------------------------------------------- --client none


def test_client_none_is_refused_rather_than_stranding_registrations(tmp_path):
    """`none` means "install without registering" to install.sh.

    Teardown narrows registration edits and nothing else, so honouring the word
    would remove the tools and leave every registration pointing at a missing
    command — the stranding the phase order exists to prevent.
    """
    home = _home(tmp_path)
    _write_json(
        home / ".cursor" / "mcp.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )
    stub = _stub_path(tmp_path)

    refused = _run(home, stub, args=("--dry-run", "--yes", "--client", "none"))
    bare = _run(home, stub, args=("--dry-run", "--yes"))

    assert refused.returncode == 2
    assert "--client none belongs to install.sh" in refused.stderr
    assert "PLAN" not in refused.stdout
    # Bare plans both halves, which is what `none` would have split apart.
    assert bare.returncode == 0
    assert "remove the 'pipefy' registration" in bare.stdout
    assert "uv tool uninstall pipefy-cli" in bare.stdout
    # Nothing was touched on either run.
    assert json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"]
