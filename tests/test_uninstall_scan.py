"""``uninstall.sh --scan`` against isolated ``HOME`` trees and a stubbed ``PATH``.

Every run gets a synthetic home and a ``PATH`` built from scratch, so no test
touches the developer's real keychain, MCP client configs, or shell rc files.
``uname``, ``uv``, ``claude``, ``security`` and ``secret-tool`` are stubs, which
also makes the macOS and Linux credential paths testable on either platform.
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

# External utilities the script calls. `python3`, `uv`, `claude`, `security`,
# `secret-tool`, `git` and `uname` are added per test instead.
_BASE_TOOLS = (
    "cat",
    "rm",
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
)


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


# An empty Secret Service. A Linux run with no `secret-tool` at all reports the
# store as uninspected and exits 2, exactly as a Darwin run with no `security`
# does, so every test that is not about that asymmetry gets a working one.
_EMPTY_SECRET_TOOL = "#!/bin/sh\nexit 1\n"


def _stub_path(
    tmp_path: Path,
    *,
    name: str = "stubbin",
    os_name: str = "Linux",
    python3: bool = True,
    git: bool = False,
    uv_tools: tuple[str, ...] | None = None,
    security: str | None = None,
    secret_tool: str | None = None,
    no_secret_tool: bool = False,
) -> Path:
    """Build a bin directory holding exactly the commands a test wants visible."""
    stub = tmp_path / name
    stub.mkdir(parents=True, exist_ok=True)
    wanted = list(_BASE_TOOLS)
    if python3:
        wanted.append("python3")
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
    if uv_tools is not None:
        listing = "".join(f"{t} v0.0.0\n" for t in uv_tools)
        _write_exec(
            stub / "uv",
            "#!/bin/sh\n"
            'if [ "$1" = "tool" ] && [ "$2" = "list" ]; then\n'
            f"    printf '%s' '{listing}'\n"
            "fi\n"
            "exit 0\n",
        )
    if security is not None:
        _write_exec(stub / "security", security)
    if secret_tool is None and not no_secret_tool:
        secret_tool = _EMPTY_SECRET_TOOL
    if secret_tool is not None:
        _write_exec(stub / "secret-tool", secret_tool)
    return stub


def _run(
    home: Path,
    stub: Path,
    *,
    cwd: Path | None = None,
    args: tuple[str, ...] = ("--scan",),
    extra_path: tuple[Path, ...] = (),
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    path_parts = [str(p) for p in extra_path] + [str(stub)]
    env = {
        "HOME": str(home),
        "PATH": ":".join(path_parts),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        # Never let a test read the developer's real uv cache.
        "UV_CACHE_DIR": str(home / "no-such-uv-cache"),
    }
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [_SH, str(_SCRIPT), *args],
        cwd=str(cwd or home),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _home(tmp_path: Path, name: str = "home") -> Path:
    home = tmp_path / name
    home.mkdir(parents=True, exist_ok=True)
    return home


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# --------------------------------------------------------------- scenarios


def test_clean_home_reports_nothing(tmp_path):
    home = _home(tmp_path)
    result = _run(home, _stub_path(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no Pipefy toolkit state found" in result.stdout
    assert "uv not on PATH" in result.stdout
    assert f"resolves to {home}/.config/pipefy" in result.stdout
    assert "Nothing on this machine was changed." in result.stdout


def test_the_claude_cli_is_never_invoked(tmp_path):
    """Client state is read from disk, so a scan works with no `claude` at all."""
    home = _home(tmp_path)
    log = tmp_path / "claude.log"
    stub = _stub_path(tmp_path)
    _write_exec(stub / "claude", f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\nexit 0\n')
    _write_json(
        home / ".claude.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )

    result = _run(home, stub)

    assert result.returncode == 1
    assert "user scope, named 'pipefy': stdio  pipefy-mcp-server" in result.stdout
    assert not log.exists()


def test_local_only_reports_binaries_uv_tools_and_stdio_registration(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )
    stub = _stub_path(tmp_path, uv_tools=("pipefy-cli", "pipefy-mcp-server"))
    shims = tmp_path / "shims"
    shims.mkdir()
    for shim in ("pipefy", "pipefy-mcp-server"):
        _write_exec(shims / shim, "#!/bin/sh\nexit 0\n")

    result = _run(home, stub, extra_path=(shims,))

    assert result.returncode == 1
    assert f"pipefy -> {shims}/pipefy (first on PATH" in result.stdout
    assert "uv tool installed: pipefy-cli" in result.stdout
    assert "uv tool installed: pipefy-mcp-server" in result.stdout
    assert "user scope, named 'pipefy': stdio  pipefy-mcp-server" in result.stdout
    assert "broken:" not in result.stdout


def test_hosted_only_reports_the_http_endpoint(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy": {"type": "http", "url": "https://mcp.pipefy.com/mcp"}
            }
        },
    )
    result = _run(home, _stub_path(tmp_path))
    assert result.returncode == 1
    assert (
        "user scope, named 'pipefy': http  https://mcp.pipefy.com/mcp" in result.stdout
    )
    assert "pipefy: not on PATH" in result.stdout
    assert "at most one registration is active per project" in result.stdout


def test_plugin_only_reports_plugin_and_marketplace_without_orphan(tmp_path):
    home = _home(tmp_path)
    plugins = home / ".claude" / "plugins"
    clone = plugins / "marketplaces" / "pipefy"
    clone.mkdir(parents=True)
    _write_json(
        plugins / "known_marketplaces.json",
        {
            "pipefy": {
                "source": {"source": "github", "repo": "pipefy/ai-toolkit"},
                "installLocation": str(clone),
            }
        },
    )
    _write_json(
        plugins / "installed_plugins.json",
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
        clone / ".mcp.json",
        {"mcpServers": {"pipefy": {"command": "uvx", "args": ["pipefy-mcp-server"]}}},
    )

    result = _run(home, _stub_path(tmp_path))

    assert result.returncode == 1
    assert "marketplace registered: pipefy" in result.stdout
    assert (
        "plugin installed: pipefy@pipefy (user scope, version 0.5.0)" in result.stdout
    )
    assert "plugin scope, named 'pipefy': stdio  uvx pipefy-mcp-server" in result.stdout
    assert "orphan" not in result.stdout


def test_hosted_plus_git_tracked_project_registration_names_the_winner(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy": {"type": "http", "url": "https://mcp.pipefy.com/mcp"}
            }
        },
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_json(
        repo / ".mcp.json",
        {"mcpServers": {"pipefy": {"command": "uvx", "args": ["pipefy-mcp-server"]}}},
    )
    stub = _stub_path(tmp_path, git=True)
    git = str(stub / "git")
    subprocess.run([git, "init", "-q", str(repo)], check=True)
    subprocess.run([git, "-C", str(repo), "add", ".mcp.json"], check=True)

    result = _run(home, stub, cwd=repo)

    assert result.returncode == 1
    out = result.stdout
    assert "one definition shadows another" in out
    assert "'pipefy' at project scope: stdio uvx pipefy-mcp-server  [active]" in out
    assert "'pipefy' at user scope: http https://mcp.pipefy.com/mcp  [shadowed]" in out
    assert "git-tracked" in out
    assert "Use disabledMcpjsonServers instead." in out
    assert "restores it from the index" in out


def test_project_scope_rejected_by_disabled_mcpjson_servers(tmp_path):
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
            },
            "projects": {str(repo): {"disabledMcpjsonServers": ["pipefy"]}},
        },
    )

    result = _run(home, _stub_path(tmp_path), cwd=repo)

    assert result.returncode == 1
    out = result.stdout
    assert (
        "'pipefy' at project scope: stdio uvx pipefy-mcp-server"
        "  [rejected by disabledMcpjsonServers]" in out
    )
    assert "'pipefy' at user scope: http https://mcp.pipefy.com/mcp  [active]" in out


def test_orphan_marketplace_without_plugin(tmp_path):
    home = _home(tmp_path)
    plugins = home / ".claude" / "plugins"
    _write_json(
        plugins / "known_marketplaces.json",
        {"pipefy": {"installLocation": str(plugins / "marketplaces" / "pipefy")}},
    )
    _write_json(plugins / "installed_plugins.json", {"version": 2, "plugins": {}})

    result = _run(home, _stub_path(tmp_path))

    assert result.returncode == 1
    assert "orphan registration: marketplace 'pipefy' is registered" in result.stdout


def test_orphan_clone_without_registration(tmp_path):
    home = _home(tmp_path)
    clone = home / ".claude" / "plugins" / "marketplaces" / "pipefy"
    clone.mkdir(parents=True)

    result = _run(home, _stub_path(tmp_path))

    assert result.returncode == 1
    assert (
        f"orphan clone: {clone} exists with no marketplace registration"
        in result.stdout
    )


def test_file_keyring_backend_lists_unescaped_accounts(tmp_path):
    home = _home(tmp_path)
    cfg = home / ".config" / "pipefy" / "keyring.cfg"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        "[pipefy]\n"
        "signin_2epipefy_2ecom_7cpipefy_2dcli = \n\tU0VDUkVUVkFMVUU=\n"
        "\n[other_2eservice]\n"
        "someone = \n\tQUJD\n",
        encoding="utf-8",
    )

    result = _run(home, _stub_path(tmp_path))

    assert result.returncode == 1
    assert "file keyring backend" in result.stdout
    assert "account: signin.pipefy.com|pipefy-cli" in result.stdout
    assert "someone" not in result.stdout
    assert "U0VDUkVUVkFMVUU=" not in result.stdout + result.stderr


def test_path_shadowed_by_a_repo_venv(tmp_path):
    home = _home(tmp_path)
    venv = tmp_path / "repo" / ".venv"
    venv_bin = venv / "bin"
    user_bin = tmp_path / "userbin"
    for directory in (venv_bin, user_bin):
        directory.mkdir(parents=True)
        _write_exec(directory / "pipefy", "#!/bin/sh\nexit 0\n")
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")

    result = _run(home, _stub_path(tmp_path), extra_path=(venv_bin, user_bin))

    assert result.returncode == 1
    out = result.stdout
    assert f"pipefy -> {venv_bin}/pipefy (first on PATH, this is what runs)" in out
    assert f"pipefy -> {user_bin}/pipefy (shadowed by the entry above)" in out
    assert "2 copies on PATH" in out
    # The venv copy is the development checkout's own binary, not an install.
    assert f"project virtualenv binary from {venv}, not an installed artifact" in out
    assert "leave it alone" in out


def test_a_plain_shim_is_not_labelled_a_virtualenv_binary(tmp_path):
    home = _home(tmp_path)
    shims = tmp_path / "shims"
    shims.mkdir()
    _write_exec(shims / "pipefy", "#!/bin/sh\nexit 0\n")

    result = _run(home, _stub_path(tmp_path), extra_path=(shims,))

    assert result.returncode == 1
    assert "project virtualenv binary" not in result.stdout


# ------------------------------------------- matched on definition, not name


def test_stdio_registration_under_another_name_is_matched(tmp_path):
    """A real environment registered the server as `pipefy-dev`, not `pipefy`."""
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy-dev": {"command": "uvx", "args": ["pipefy-mcp-server"]}
            }
        },
    )

    result = _run(home, _stub_path(tmp_path))

    assert result.returncode == 1
    assert (
        "user scope, named 'pipefy-dev': stdio  uvx pipefy-mcp-server" in result.stdout
    )
    assert "unverified" not in result.stdout


def test_absolute_command_path_and_bare_binary_both_match(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".cursor" / "mcp.json",
        {
            "mcpServers": {
                "anything-at-all": {"command": "/opt/tools/bin/pipefy-mcp-server"}
            }
        },
    )

    result = _run(home, _stub_path(tmp_path))

    assert result.returncode == 1
    assert "client:cursor scope, named 'anything-at-all': stdio" in result.stdout


def test_hosted_endpoint_matched_by_host_under_any_name(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "work": {
                    "type": "http",
                    "url": "https://MCP.PIPEFY.COM:443/mcp?x=1",
                }
            }
        },
    )

    result = _run(home, _stub_path(tmp_path))

    assert result.returncode == 1
    assert "user scope, named 'work': http" in result.stdout
    assert "unverified" not in result.stdout


def test_a_url_with_no_type_is_matched_and_the_caveat_names_the_reader(tmp_path):
    """Whether a type-less url starts is the reader's business, not the rule's.

    Cursor and Codex serve a bare ``url`` over HTTP; Claude Code reads an entry
    with no ``type`` as stdio and skips it. Judging the shape by one client's
    rule would leave the registration invisible in the others, so it is matched
    everywhere and the caveat is attached where it applies.
    """
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {"mcpServers": {"work": {"url": "https://mcp.pipefy.com/mcp"}}},
    )
    _write_json(
        home / ".cursor" / "mcp.json",
        {"mcpServers": {"remote": {"url": "https://mcp.pipefy.com/mcp"}}},
    )

    result = _run(home, _stub_path(tmp_path))
    out = result.stdout

    assert result.returncode == 1
    assert "user scope, named 'work': untyped-url" in out
    assert "client:cursor scope, named 'remote': untyped-url" in out
    assert "unverified" not in out
    # The caveat belongs to the config Claude Code reads, and to no other.
    claude_block = out.split("named 'work'", 1)[1].split("named 'remote'", 1)[0]
    cursor_block = out.split("named 'remote'", 1)[1]
    assert "claude-code reads such an entry as stdio" in claude_block
    assert "reads such an entry as stdio" not in cursor_block


def test_a_registration_hides_behind_neither_of_its_two_fields(tmp_path):
    """Both halves of the rule are read, so one field cannot mask the other."""
    home = _home(tmp_path)
    _write_json(
        home / ".cursor" / "mcp.json",
        {
            "mcpServers": {
                "a": {
                    "command": "pipefy-mcp-server",
                    "url": "https://other.example/mcp",
                },
                "b": {"command": "some-proxy", "url": "https://mcp.pipefy.com/mcp"},
                "c": {"command": "some-proxy", "url": "https://other.example/mcp"},
            }
        },
    )

    result = _run(home, _stub_path(tmp_path))
    out = result.stdout

    assert "named 'a': stdio" in out
    assert "named 'b': untyped-url" in out
    assert "named 'c'" not in out


def test_two_differently_named_servers_both_active_is_a_conflict(tmp_path):
    """The one-server invariant, made checkable now that names are data."""
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy": {"type": "http", "url": "https://mcp.pipefy.com/mcp"},
                "pipefy-dev": {"command": "uvx", "args": ["pipefy-mcp-server"]},
            }
        },
    )

    result = _run(home, _stub_path(tmp_path))

    out = result.stdout
    assert result.returncode == 1
    assert "more than one server is active here" in out
    assert "'pipefy' at user scope: http https://mcp.pipefy.com/mcp  [active]" in out
    assert "'pipefy-dev' at user scope: stdio uvx pipefy-mcp-server  [active]" in out


def test_http_registration_off_the_documented_host_is_unverified_not_claimed(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "pipefy-alt": {
                    "type": "http",
                    "url": "https://alt-endpoint.pipefy.example/mcp",
                }
            }
        },
    )

    result = _run(home, _stub_path(tmp_path))

    out = result.stdout
    assert result.returncode == 1
    assert (
        "unverified: 'pipefy-alt' at user scope is an HTTP registration that is not"
        " the documented hosted endpoint" in out
    )
    assert "decide whether this one is yours" in out
    # An unverified entry is never treated as a real registration.
    assert "more than one server is active" not in out


def test_an_env_block_of_ours_makes_an_unknown_entry_unverified(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "mystery": {
                    "command": "some-other-server",
                    "env": {"PIPEFY_TOKEN": "x"},
                }
            }
        },
    )

    result = _run(home, _stub_path(tmp_path))

    assert result.returncode == 1
    assert (
        "unverified: 'mystery' at user scope does not run pipefy-mcp-server"
        in result.stdout
    )


def test_codex_section_under_another_name_is_matched_by_its_command(tmp_path):
    home = _home(tmp_path)
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text(
        '[mcp_servers.unrelated]\ncommand = "other-server"\n\n'
        '[mcp_servers.work]\ncommand = "uvx"\nargs = ["pipefy-mcp-server"]\n\n'
        '[profiles.default]\nmodel = "x"\n',
        encoding="utf-8",
    )

    result = _run(home, _stub_path(tmp_path))

    out = result.stdout
    assert result.returncode == 1
    assert "codex, section [mcp_servers.work]: uvx pipefy-mcp-server" in out
    assert "mcp_servers.unrelated" not in out


def test_codex_section_pointing_at_the_hosted_host_is_matched(tmp_path):
    home = _home(tmp_path)
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text(
        '[mcp_servers.remote]\nurl = "https://mcp.pipefy.com/mcp"\n',
        encoding="utf-8",
    )

    result = _run(home, _stub_path(tmp_path))

    assert result.returncode == 1
    assert (
        "codex, section [mcp_servers.remote]: https://mcp.pipefy.com/mcp"
        in result.stdout
    )


def test_secret_in_a_client_config_env_block_is_named_but_never_printed(tmp_path):
    sentinel = "s3cr3t-token-value-do-not-print"
    home = _home(tmp_path)
    _write_json(
        home / ".claude" / "settings.json",
        {"env": {"PIPEFY_TOKEN": sentinel, "EDITOR": "vim"}},
    )
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
        f'export PIPEFY_TOKEN="{sentinel}"\nexport EDITOR=vim\n', encoding="utf-8"
    )

    result = _run(
        home,
        _stub_path(tmp_path),
        env_extra={"PIPEFY_TOKEN": sentinel, "PIPEFY_ORG_ID": "9876543210987"},
    )

    out = result.stdout
    assert result.returncode == 1
    assert "PIPEFY_TOKEN (credential) in" in out
    assert "env.PIPEFY_TOKEN" in out
    assert "mcpServers.pipefy.env.PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET" in out
    assert "set in this process environment: PIPEFY_TOKEN (credential)" in out
    assert "set in this process environment: PIPEFY_ORG_ID (configuration)" in out
    assert f"PIPEFY_TOKEN assigned in {home}/.zshrc (line 1)" in out
    assert sentinel not in out
    assert sentinel not in result.stderr
    assert "9876543210987" not in out


def test_broken_registration_names_the_unresolvable_command(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )
    result = _run(home, _stub_path(tmp_path))
    assert result.returncode == 1
    assert (
        "broken: command 'pipefy-mcp-server' does not resolve on PATH" in result.stdout
    )


def test_codex_section_is_detected_by_its_header(tmp_path):
    home = _home(tmp_path)
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text(
        '[mcp_servers.other]\ncommand = "other-server"\n\n'
        '[mcp_servers.pipefy]\ncommand = "pipefy-mcp-server"\n\n'
        '[profiles.default]\nmodel = "gpt"\n',
        encoding="utf-8",
    )

    result = _run(home, _stub_path(tmp_path))

    assert result.returncode == 1
    assert "codex, section [mcp_servers.pipefy]: pipefy-mcp-server" in result.stdout


def test_config_dir_honours_xdg_config_home(tmp_path):
    home = _home(tmp_path)
    xdg = tmp_path / "xdg"
    (xdg / "pipefy").mkdir(parents=True)
    (xdg / "pipefy" / "refresh.lock").write_text("", encoding="utf-8")

    result = _run(home, _stub_path(tmp_path), env_extra={"XDG_CONFIG_HOME": str(xdg)})

    assert result.returncode == 1
    assert f"resolves to {xdg}/pipefy" in result.stdout
    assert f"{xdg}/pipefy/refresh.lock" in result.stdout
    assert "not idempotent" in result.stdout


def test_completions_and_skills(tmp_path):
    home = _home(tmp_path)
    (home / ".bash_completions").mkdir()
    (home / ".bash_completions" / "pipefy.sh").write_text("", encoding="utf-8")
    (home / ".bashrc").write_text(
        f"source {home}/.bash_completions/pipefy.sh\n", encoding="utf-8"
    )
    (home / ".zfunc").mkdir()
    (home / ".zfunc" / "_pipefy").write_text("#compdef pipefy\n", encoding="utf-8")
    (home / ".zshrc").write_text("fpath+=~/.zfunc\n", encoding="utf-8")
    _install_skills(home, "pipefy-reports", "pipefy-pipes-and-cards")

    result = _run(home, _stub_path(tmp_path))

    out = result.stdout
    assert result.returncode == 1
    assert f"{home}/.bash_completions/pipefy.sh" in out
    assert f"{home}/.zfunc/_pipefy" in out
    assert "sources the completion script (line 1)" in out
    assert "adds ~/.zfunc to fpath; shared with other tools" in out
    assert "2 pipefy-* skills from this toolkit" in out


# `npx skills add` is the only thing that records where a skill came from, in a
# lock file beside the shared store it writes into. Nothing else on disk carries
# provenance, so these helpers reproduce the two halves it leaves behind.
_SKILL_LOCK = ".agents/.skill-lock.json"


def _lock_entry(source: str, skill_path: str) -> dict:
    return {
        "installedAt": "2026-01-01T00:00:00.000Z",
        "skillPath": skill_path,
        "source": source,
        "sourceType": "github",
        "sourceUrl": f"https://github.com/{source}.git",
    }


def _install_skills(home: Path, *names: str, source: str = "pipefy/ai-toolkit") -> None:
    """A skill directory plus the lock entry that says where it came from."""
    lock_path = home / _SKILL_LOCK
    lock = (
        json.loads(lock_path.read_text(encoding="utf-8"))
        if lock_path.exists()
        else {"version": 3, "skills": {}}
    )
    for name in names:
        directory = home / ".claude" / "skills" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        lock["skills"][name] = _lock_entry(source, f"skills/{name}/SKILL.md")
    _write_json(lock_path, lock)


def _hand_written_skill(home: Path, name: str) -> Path:
    """A skill under the same name prefix that no installer put there."""
    directory = home / ".claude" / "skills" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text("---\nname: mine\n---\n", encoding="utf-8")
    return directory


def test_a_skill_with_no_recorded_source_is_reported_and_never_claimed(tmp_path):
    home = _home(tmp_path)
    _hand_written_skill(home, "pipefy-tasks")

    result = _run(home, _stub_path(tmp_path))

    out = result.stdout
    assert "pipefy-tasks" in out
    assert "nothing records where it came from, so it is left alone" in out
    assert "no pipefy-* skills from this toolkit" in out
    # Someone else's directory is not this toolkit's state, so it is not a
    # finding either.
    assert result.returncode == 0, out


def test_a_skill_installed_from_another_repository_is_left_alone(tmp_path):
    home = _home(tmp_path)
    _install_skills(home, "pipefy-tasks", source="someone-else/their-skills")

    result = _run(home, _stub_path(tmp_path))

    assert result.returncode == 0, result.stdout
    assert "came from someone-else/their-skills, not this toolkit" in result.stdout


def test_a_missing_secret_tool_is_uninspected_rather_than_clean(tmp_path):
    """The same call as a missing `security` on Darwin: unreadable is not clean."""
    home = _home(tmp_path)

    result = _run(home, _stub_path(tmp_path, no_secret_tool=True))

    assert result.returncode == 2, result.stdout
    assert "keychain not inspected — 'secret-tool' not on PATH" in result.stdout
    assert "sources could not be inspected" in result.stdout


def test_a_scan_writes_nothing_to_stderr(tmp_path):
    """`client_rows` streams, and a consumer that exits early closed the pipe.

    dash reported the resulting EPIPE as `printf: I/O error`. Whether the
    producer is still writing when the consumer goes depends on the pipe
    buffer, so this reproduces on Linux and not on macOS: it guards the
    regression where CI runs, and passes either way where it does not.
    """
    home = _home(tmp_path)

    result = _run(home, _stub_path(tmp_path))

    assert "I/O error" not in result.stderr, result.stderr
    assert result.stderr == "", result.stderr


# --------------------------------------------------------------- keychain


_MACOS_DUMP = """keychain: "/Users/x/Library/Keychains/login.keychain-db"
version: 512
class: "genp"
attributes:
    0x00000007 <blob>="pipefy"
    "acct"<blob>="signin.pipefy.com|pipefy-cli"
    "svce"<blob>="pipefy"
keychain: "/Users/x/Library/Keychains/login.keychain-db"
version: 512
class: "genp"
attributes:
    0x00000007 <blob>="Unrelated"
    "acct"<blob>="someone@pipefy.com"
    "svce"<blob>="Some pipefy-ish service"
keychain: "/Users/x/Library/Keychains/login.keychain-db"
version: 512
class: "genp"
attributes:
    0x00000007 <blob>="pipefy"
    "acct"<blob>="signin.other.example|pipefy-cli"
    "svce"<blob>="pipefy"
"""


def _security_stub(log: Path) -> str:
    dump = _MACOS_DUMP.replace("'", "'\\''")
    return (
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        'svc=""\n'
        'prev=""\n'
        'for arg in "$@"; do\n'
        '    if [ "$prev" = "-s" ]; then svc="$arg"; fi\n'
        '    prev="$arg"\n'
        "done\n"
        'case "$1" in\n'
        "    find-generic-password)\n"
        '        [ "$svc" = "pipefy" ] && exit 0\n'
        "        exit 44\n"
        "        ;;\n"
        f"    dump-keychain) printf '%s' '{dump}' ; exit 0 ;;\n"
        "esac\n"
        "exit 1\n"
    )


def test_macos_keychain_entries_are_enumerated_without_reading_secrets(tmp_path):
    home = _home(tmp_path)
    log = tmp_path / "security.log"
    stub = _stub_path(tmp_path, os_name="Darwin", security=_security_stub(log))

    result = _run(home, stub)

    out = result.stdout
    assert result.returncode == 1
    assert "keychain: service pipefy, account signin.pipefy.com|pipefy-cli" in out
    assert "keychain: service pipefy, account signin.other.example|pipefy-cli" in out
    assert "someone@pipefy.com" not in out
    invocations = log.read_text(encoding="utf-8").split("\n")
    assert any(line.startswith("find-generic-password") for line in invocations)
    # -w and -g are the flags that read a secret and raise an access prompt.
    for line in invocations:
        assert " -w" not in line
        assert " -g" not in line


def test_macos_keychain_absent_is_reported_without_dumping(tmp_path):
    home = _home(tmp_path)
    log = tmp_path / "security.log"
    stub = _stub_path(
        tmp_path,
        os_name="Darwin",
        security=(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$*" >> "{log}"\n'
            'case "$1" in find-generic-password) exit 44 ;; esac\n'
            "exit 1\n"
        ),
    )

    result = _run(home, stub)

    assert result.returncode == 0
    assert "keychain: no item with service 'pipefy'" in result.stdout
    assert (
        "keychain: no wrapping key with service 'pipefy-wrapping-key'" in result.stdout
    )
    assert "dump-keychain" not in log.read_text(encoding="utf-8")


def test_macos_wrapping_key_present_is_planned_with_canonical_identity(tmp_path):
    from pipefy_auth.keychain_choice import (
        WRAPPING_KEYCHAIN_ACCOUNT,
        WRAPPING_KEYCHAIN_SERVICE,
    )

    home = _home(tmp_path)
    log = tmp_path / "security.log"
    stub = _stub_path(
        tmp_path,
        os_name="Darwin",
        security=(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$*" >> "{log}"\n'
            'svc=""\n'
            'prev=""\n'
            'for arg in "$@"; do\n'
            '    if [ "$prev" = "-s" ]; then svc="$arg"; fi\n'
            '    prev="$arg"\n'
            "done\n"
            'case "$1" in\n'
            "    find-generic-password)\n"
            f'        [ "$svc" = "{WRAPPING_KEYCHAIN_SERVICE}" ] && exit 0\n'
            "        exit 44\n"
            "        ;;\n"
            "    dump-keychain) exit 0 ;;\n"
            "esac\n"
            "exit 1\n"
        ),
    )

    result = _run(home, stub)

    assert result.returncode == 1
    assert (
        f"keychain: wrapping key service {WRAPPING_KEYCHAIN_SERVICE}, "
        f"account {WRAPPING_KEYCHAIN_ACCOUNT}"
    ) in result.stdout
    invocations = log.read_text(encoding="utf-8").split("\n")
    assert any(
        WRAPPING_KEYCHAIN_SERVICE in line and line.startswith("find-generic-password")
        for line in invocations
    )


def test_linux_secret_service_entries_never_leak_the_secret(tmp_path):
    home = _home(tmp_path)
    sentinel = "refresh-token-value"
    log = tmp_path / "secret-tool.log"
    payload = (
        "[/org/freedesktop/secrets/collection/login/1]\\n"
        "label = pipefy\\n"
        f"secret = {sentinel}\\n"
        "attribute.service = pipefy\\n"
        "attribute.username = signin.pipefy.com|pipefy-cli\\n"
    )
    stub = _stub_path(
        tmp_path,
        os_name="Linux",
        secret_tool=(
            f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\nprintf "{payload}"\n'
        ),
    )

    result = _run(home, stub)

    assert result.returncode == 1
    assert (
        "keychain: service pipefy, account signin.pipefy.com|pipefy-cli"
        in result.stdout
    )
    assert sentinel not in result.stdout
    assert sentinel not in result.stderr
    assert "--unlock" not in log.read_text(encoding="utf-8")


# ------------------------------------------------------------------- noise


def test_noise_home_produces_zero_findings(tmp_path):
    """Unrelated uses of the word must not register. See failure mode 6 in #536."""
    home = _home(tmp_path)
    (home / "pipefy-notes").mkdir()
    (home / "src" / "pipefy-clone").mkdir(parents=True)
    (home / ".gitconfig").write_text(
        "[user]\n    email = someone@pipefy.com\n", encoding="utf-8"
    )
    (home / ".zshrc").write_text(
        "# pipefy helpers\n"
        'export MY_PIPEFY_TOKEN="x"\n'
        'export PIPEFY_TOKEN_BACKUP="x"\n'
        'export EDITOR="vim"\n'
        'alias pipefy="echo no"\n',
        encoding="utf-8",
    )
    _write_json(
        home / ".claude.json",
        {
            "mcpServers": {
                "other": {"type": "http", "url": "https://builder.pipefy.example/mcp"},
                # A host that contains "pipefy" and is not the documented
                # endpoint: unrelated infrastructure, matched by nothing.
                "other-agent-builder": {
                    "type": "http",
                    "url": "https://mcp-ui.pipefy-unrelated.example/mcp",
                },
                # Argument-position sloppiness: a runner, and a path that
                # contains "pipefy", but no exact pipefy-mcp-server argument.
                "some-other-tool": {
                    "command": "npx",
                    "args": [
                        "some-other-mcp",
                        "--root",
                        str(home / "pipefy-notes" / "workspace"),
                    ],
                },
            },
            "projects": {str(home / "pipefy-notes"): {"allowedTools": []}},
        },
    )
    _write_json(
        home / ".cursor" / "mcp.json",
        {"mcpServers": {"notpipefy": {"command": "notpipefy-server"}}},
    )
    _write_json(
        home / ".claude" / "settings.json",
        {
            "env": {"PIPEFY_TOKENISER": "x"},
            "extraKnownMarketplaces": {"pipefy-fork": {}},
        },
    )
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text(
        '# pipefy notes\n[mcp_servers.pipefy-other]\ncommand = "other"\n',
        encoding="utf-8",
    )
    for skill in ("pipefy", "my-pipefy-helper"):
        directory = home / ".claude" / "skills" / skill
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    (home / ".claude" / "plugins" / "marketplaces" / "pipefy-fork").mkdir(parents=True)
    workdir = home / "pipefy-notes"

    result = _run(
        home,
        _stub_path(tmp_path),
        cwd=workdir,
        env_extra={"MY_PIPEFY_TOKEN": "x", "PIPEFY_TOKENISER": "x"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no Pipefy toolkit state found" in result.stdout


# ----------------------------------------------- session store, uv cache


def test_effective_session_store_defaults_to_the_os_keychain(tmp_path):
    result = _run(_home(tmp_path), _stub_path(tmp_path))
    assert result.returncode == 0
    assert "effective session store: the OS keychain (no override in effect)" in (
        result.stdout
    )
    assert "PIPEFY_KEYCHAIN_BACKEND is set in" not in result.stdout


def test_effective_session_store_from_the_process_environment(tmp_path):
    home = _home(tmp_path)
    (home / ".zshrc").write_text(
        "export PIPEFY_KEYCHAIN_BACKEND=file\n", encoding="utf-8"
    )

    result = _run(
        home, _stub_path(tmp_path), env_extra={"PIPEFY_KEYCHAIN_BACKEND": "file"}
    )

    out = result.stdout
    assert result.returncode == 1
    assert (
        f"effective session store: the file backend at {home}/.config/pipefy/keyring.cfg"
        in out
    )
    assert "PIPEFY_KEYCHAIN_BACKEND is set in the process environment" in out
    assert f"PIPEFY_KEYCHAIN_BACKEND assigned in {home}/.zshrc (line 1)" in out
    # The hazard the owner hit: drop the line, the store silently changes.
    assert "the next login" in out and "writes to the OS keychain instead" in out
    assert "still signed in and invisible to a keychain-only sweep" in out
    assert "wrapping artifacts are checked below" in out


def test_effective_session_store_from_config_toml(tmp_path):
    home = _home(tmp_path)
    toml = home / ".config" / "pipefy" / "config.toml"
    toml.parent.mkdir(parents=True)
    toml.write_text(
        'keychain_backend = "file"\n\n[other]\nkeychain_backend = "auto"\n',
        encoding="utf-8",
    )

    result = _run(home, _stub_path(tmp_path))

    out = result.stdout
    assert result.returncode == 1
    assert "effective session store: the file backend" in out
    assert f"PIPEFY_KEYCHAIN_BACKEND is set in {toml}" in out


def test_effective_session_store_encrypted_from_the_process_environment(tmp_path):
    home = _home(tmp_path)
    result = _run(
        home, _stub_path(tmp_path), env_extra={"PIPEFY_KEYCHAIN_BACKEND": "encrypted"}
    )
    out = result.stdout
    assert (
        f"effective session store: the encrypted backend at {home}/.config/pipefy/session.enc"
        in out
    )
    assert "PIPEFY_KEYCHAIN_BACKEND is set in the process environment" in out


def test_encrypted_session_file_is_planned_for_removal(tmp_path):
    home = _home(tmp_path)
    enc = home / ".config" / "pipefy" / "session.enc"
    wrap = home / ".config" / "pipefy" / "wrapping.key"
    enc.parent.mkdir(parents=True)
    enc.write_bytes(b"ciphertext")
    wrap.write_bytes(b"dpapi")

    result = _run(home, _stub_path(tmp_path))

    out = result.stdout
    assert result.returncode == 1
    assert f"encrypted session store: {enc}" in out
    assert f"encrypted wrapping key: {wrap}" in out
    assert f"{enc} (reported under stored credentials)" in out
    assert f"{wrap} (reported under stored credentials)" in out


def test_an_unrecognized_backend_value_is_never_echoed(tmp_path):
    home = _home(tmp_path)
    sentinel = "some-unexpected-backend-value"
    result = _run(
        home, _stub_path(tmp_path), env_extra={"PIPEFY_KEYCHAIN_BACKEND": sentinel}
    )
    assert "holds an unrecognized value" in result.stdout
    assert sentinel not in result.stdout
    assert sentinel not in result.stderr


def test_uv_cache_editable_entries_are_counted_and_fenced_off(tmp_path):
    home = _home(tmp_path)
    cache = tmp_path / "uvcache"
    archive = cache / "archive-v0" / "abc123"
    archive.mkdir(parents=True)
    for name in ("_pipefy_editable_impl_aaa.pth", "_other_editable_impl_bbb.pth"):
        (archive / name).write_text("/some/repo/src\n", encoding="utf-8")
    (archive / "unrelated.pth").write_text("", encoding="utf-8")

    result = _run(home, _stub_path(tmp_path), env_extra={"UV_CACHE_DIR": str(cache)})

    out = result.stdout
    assert f"cache directory: {cache}" in out
    assert "2 editable-install entries" in out
    assert "Do not chase them" in out
    assert "'uv cache clean <package>' does not remove them anyway" in out
    # The cache is never itself a finding: nothing here is ours to remove.
    assert result.returncode == 0


def test_uv_cache_warns_against_a_bare_clean_and_the_hardlink_hazard(tmp_path):
    home = _home(tmp_path)
    cache = tmp_path / "uvcache"
    cache.mkdir()

    result = _run(home, _stub_path(tmp_path), env_extra={"UV_CACHE_DIR": str(cache)})

    out = result.stdout
    assert "Never run a bare 'uv cache clean'" in out
    assert "clears the" in out and "cache for every package on this machine" in out
    assert "hardlinks tool environments" in out
    assert "Prefer 'uv cache prune'" in out
    # The closing block repeats it, since that is where a reader looks for a fix.
    assert "Never run a bare 'uv cache clean'." in out


def test_marketplace_removal_is_flagged_as_not_durable(tmp_path):
    home = _home(tmp_path)
    plugins = home / ".claude" / "plugins"
    _write_json(
        plugins / "known_marketplaces.json",
        {"pipefy": {"installLocation": str(plugins / "marketplaces" / "pipefy")}},
    )
    _write_json(plugins / "installed_plugins.json", {"version": 2, "plugins": {}})

    result = _run(home, _stub_path(tmp_path))

    out = result.stdout
    assert result.returncode == 1
    assert "Removing a marketplace is not necessarily durable" in out
    assert "a later session re-adds it" in out
    assert "extraKnownMarketplaces" in out
    assert "confirm" in out and "with a fresh session" in out


# ------------------------------------------------------- degradation, flags


def test_without_python3_json_sources_are_uninspected_and_exit_is_two(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )
    result = _run(home, _stub_path(tmp_path, python3=False))

    out = result.stdout
    assert result.returncode == 2
    assert "python3:   not found" in out
    assert "JSON client configs not inspected — python3 unavailable" in out
    assert "plugin registry not inspected — python3 unavailable" in out
    assert "client config env blocks not inspected — python3 unavailable" in out
    assert "sources could not be inspected" in out
    # Non-JSON sources still work without python3.
    assert "codex: no " in out
    assert "no pipefy-* skills" in out or "no " in out


def test_unreadable_json_source_exits_two(tmp_path):
    home = _home(tmp_path)
    (home / ".claude.json").write_text("{not json", encoding="utf-8")
    result = _run(home, _stub_path(tmp_path))
    assert result.returncode == 2
    assert "not valid JSON" in result.stdout


def test_help_exits_zero(tmp_path):
    result = _run(_home(tmp_path), _stub_path(tmp_path), args=("--help",))
    assert result.returncode == 0
    assert "Report Pipefy toolkit state" in result.stdout
    assert "--scan" in result.stdout


def test_unknown_flag_exits_two(tmp_path):
    result = _run(_home(tmp_path), _stub_path(tmp_path), args=("--nope",))
    assert result.returncode == 2
    assert "Unknown flag" in result.stderr


def test_client_flag_does_not_narrow_detection(tmp_path):
    home = _home(tmp_path)
    _write_json(
        home / ".cursor" / "mcp.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )
    result = _run(home, _stub_path(tmp_path), args=("--scan", "--client", "codex"))
    assert result.returncode == 1
    assert "detection sweeps every client regardless" in result.stdout
    assert (
        "client:cursor scope, named 'pipefy': stdio  pipefy-mcp-server" in result.stdout
    )


def test_dry_run_is_accepted_and_changes_nothing(tmp_path):
    home = _home(tmp_path)
    before = sorted(p.name for p in home.iterdir())
    result = _run(home, _stub_path(tmp_path), args=("--scan", "--dry-run"))
    assert result.returncode == 0
    assert "--dry-run has no effect" in result.stdout
    assert sorted(p.name for p in home.iterdir()) == before


def test_a_scan_reaches_no_removal_verb(tmp_path):
    """A scan cannot damage anything, and the proof is behavioural.

    The script does remove things in its other modes, so the guarantee is no
    longer a grep for `rm`. It is that `--scan` leaves the tree byte-identical
    and never calls a command that could change it.
    """
    home = _home(tmp_path)
    _write_json(
        home / ".claude.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )
    _write_json(
        home / ".cursor" / "mcp.json",
        {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}},
    )
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text(
        '[mcp_servers.pipefy]\ncommand = "pipefy-mcp-server"\n', encoding="utf-8"
    )
    (home / ".zshrc").write_text('export PIPEFY_TOKEN="x"\n', encoding="utf-8")
    config = home / ".config" / "pipefy"
    config.mkdir(parents=True)
    (config / "refresh.lock").write_text("", encoding="utf-8")
    stub = _stub_path(tmp_path, uv_tools=("pipefy-cli",))
    log = tmp_path / "verbs.log"
    for name in ("claude", "security", "secret-tool", "pipefy"):
        _write_exec(
            stub / name,
            f'#!/bin/sh\nprintf "{name} %s\\n" "$*" >> "{log}"\nexit 0\n',
        )

    before = {
        str(p.relative_to(home)): p.read_bytes() for p in home.rglob("*") if p.is_file()
    }
    result = _run(home, stub)
    after = {
        str(p.relative_to(home)): p.read_bytes() for p in home.rglob("*") if p.is_file()
    }

    assert result.returncode == 1
    assert after == before
    # `run` echoes every command it executes; a scan executes none.
    assert "\n+ " not in "\n" + result.stderr
    # The keychain is read, never written, and no client CLI is called at all.
    invocations = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    assert invocations == ["secret-tool search service pipefy"], invocations


# ------------------------------------------------------------- name lists


def _shell_list(name: str) -> set[str]:
    body = _SCRIPT.read_text(encoding="utf-8")
    match = re.search(rf'^{name}="([^"]*)"', body, re.MULTILINE)
    assert match, f"{name} not found in uninstall.sh"
    return set(match.group(1).split())


def _settings_env_names() -> set[str]:
    from pipefy_auth.settings import AuthSettings, JwtValidationSettings
    from pipefy_mcp.settings import IpaasSettings, McpSettings, ResourceServerSettings
    from pipefy_sdk.settings import PipefySettings

    names: set[str] = set()
    for model in (
        AuthSettings,
        JwtValidationSettings,
        PipefySettings,
        McpSettings,
        ResourceServerSettings,
        IpaasSettings,
    ):
        prefix = model.model_config.get("env_prefix", "")
        for field_name, field in model.model_fields.items():
            alias = field.validation_alias
            choices = getattr(alias, "choices", None) if alias is not None else None
            if choices:
                names.update(str(c) for c in choices)
            elif alias is not None:
                names.add(str(alias))
            else:
                names.add((prefix + field_name).upper())
    return {n for n in names if n.startswith("PIPEFY_")}


def _documented_env_names() -> set[str]:
    text = (_REPO_ROOT / "docs" / "config.md").read_text(encoding="utf-8")
    return set(re.findall(r"^\| `(PIPEFY_[A-Z0-9_<>]+)`", text, re.MULTILINE))


def test_credential_env_list_matches_its_python_source():
    """The secret tier: deliberately wider than `_session_masking_env_vars()`.

    That function answers "what outranks a stored session", which is narrower
    than "what is a secret" — the iPaaS client secret grants access without
    masking anything, so it belongs here even though the CLI never reports it.
    """
    from pipefy_auth.settings import _LEGACY_ENV_KEYS_TO_NEW

    expected = (
        {"PIPEFY_TOKEN", "PIPEFY_IPAAS_OAUTH_CLIENT_SECRET"}
        | set(_LEGACY_ENV_KEYS_TO_NEW)
        | set(_LEGACY_ENV_KEYS_TO_NEW.values())
    )
    assert _shell_list("CRED_ENV_NAMES") == expected


def test_config_env_list_matches_the_settings_models_and_docs():
    credentials = _shell_list("CRED_ENV_NAMES")
    # PIPEFY_IPAAS_CONNECTION_<NAME> is a prefix convention resolved at call
    # time, not a variable name, so it has no place in an exact-name list.
    expected = (
        (_settings_env_names() | _documented_env_names())
        - credentials
        - {"PIPEFY_IPAAS_CONNECTION_<NAME>"}
    )
    assert _shell_list("CONFIG_ENV_NAMES") == expected


def test_the_two_lists_are_disjoint_and_sorted():
    credentials = _shell_list("CRED_ENV_NAMES")
    config = _shell_list("CONFIG_ENV_NAMES")
    assert not credentials & config
    body = _SCRIPT.read_text(encoding="utf-8")
    match = re.search(r'^CONFIG_ENV_NAMES="([^"]*)"', body, re.MULTILINE)
    assert match
    listed = match.group(1).split()
    assert listed == sorted(listed)
