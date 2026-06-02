#!/bin/sh
# install.sh — one-command installer for Pipefy CLI + MCP server.
#
# Resolves the latest GitHub Release tag (or a tag passed via --version),
# discovers its wheel assets, installs the CLI and MCP server via
# `uv tool install`, optionally installs skills via `npx skills add`, and
# registers the MCP server with the chosen client (a config-file write for
# most clients; `claude mcp add` at user scope for Claude Code).

set -eu

REPO="gbrlcustodio/pipefy-mcp-server"
TOOLS="pipefy_cli pipefy_mcp_server"  # wheels installed as standalone uv tools

YES=0
NO_SKILLS=0
CLIENT=""
TAG=""
PREFIX=""
ALLOW_ROOT=0
DRY_RUN=0

OS=""
WHEEL_URLS=""
UV_INSTALLED_THIS_RUN=0
PYTHON_OVERRIDE=""

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
err() { printf 'error: %s\n' "$*" >&2; exit 1; }

run() {
    printf '+ %s\n' "$*" >&2
    if [ "$DRY_RUN" -eq 1 ]; then
        return 0
    fi
    "$@"
}

# Like `run`, but captures stdout+stderr; prints them only if the command
# fails. Use for `uv tool install` and similar commands that produce a long
# package-list summary on success the user doesn't need to see (uv's own
# --quiet flag doesn't suppress that summary on every uv version).
run_quiet() {
    printf '+ %s\n' "$*" >&2
    if [ "$DRY_RUN" -eq 1 ]; then
        return 0
    fi
    _rq_log=$(mktemp "${TMPDIR:-/tmp}/pipefy-install.XXXXXX") \
        || err "mktemp failed (TMPDIR=${TMPDIR:-/tmp})"
    # Clean up the tempfile even on signal (Ctrl-C between mktemp and rm).
    trap 'rm -f "$_rq_log"' EXIT INT TERM
    if "$@" >"$_rq_log" 2>&1; then
        rm -f "$_rq_log"
        trap - EXIT INT TERM
        return 0
    fi
    _rq_rc=$?
    cat "$_rq_log" >&2 || true
    rm -f "$_rq_log"
    trap - EXIT INT TERM
    return "$_rq_rc"
}

print_help() {
    cat <<EOF
Usage: install.sh [OPTIONS]

Install the Pipefy CLI and MCP server via uv, optionally add skills,
and register the MCP server with an MCP client.

Options:
  --yes, -y           Skip all confirmation prompts.
  --no-skills         Skip the skills installation step.
  --client <id>       Register the MCP server for this client.
                      One of: claude-code, claude-desktop, cursor, codex, none.
                      claude-code registers via 'claude mcp add' at user scope
                      (overrides the plugin's bundled server); the others write
                      the client's own config file.
                      Defaults to 'none' (prints snippet to paste).
  --version <tag>     Install a specific GitHub Release tag (e.g. v0.2.0-beta.2).
                      Defaults to the most recent release (incl. prereleases).
  --prefix <dir>      Pass through as UV_TOOL_DIR for uv tool install.
  --allow-root        Allow running as root (refuses by default).
  --dry-run           Print commands without executing them.
  -h, --help          Show this help.

Examples:
  curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh \\
    | sh -s -- --client cursor

  ./install.sh --yes --client claude-desktop
  ./install.sh --dry-run --version v0.2.0-beta.2
EOF
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --yes|-y) YES=1; shift ;;
            --no-skills) NO_SKILLS=1; shift ;;
            --client) [ $# -ge 2 ] || err "--client requires a value"; CLIENT="$2"; shift 2 ;;
            --client=*) CLIENT="${1#--client=}"; shift ;;
            --version) [ $# -ge 2 ] || err "--version requires a value"; TAG="$2"; shift 2 ;;
            --version=*) TAG="${1#--version=}"; shift ;;
            --prefix) [ $# -ge 2 ] || err "--prefix requires a value"; PREFIX="$2"; shift 2 ;;
            --prefix=*) PREFIX="${1#--prefix=}"; shift ;;
            --allow-root) ALLOW_ROOT=1; shift ;;
            --dry-run) DRY_RUN=1; shift ;;
            -h|--help) print_help; exit 0 ;;
            *) err "Unknown flag: $1 (try --help)" ;;
        esac
    done
    case "$CLIENT" in
        ""|claude-code|claude-desktop|cursor|codex|none) ;;
        *) err "Invalid --client: $CLIENT (use claude-code|claude-desktop|cursor|codex|none)" ;;
    esac
}

refuse_root() {
    if [ "$(id -u)" = "0" ] && [ "$ALLOW_ROOT" -eq 0 ]; then
        err "Refusing to run as root. Re-run as a regular user, or pass --allow-root."
    fi
}

detect_platform() {
    OS="$(uname -s)"
    case "$OS" in
        Darwin|Linux) ;;
        *) err "Unsupported OS: $OS. install.sh supports macOS and Linux." ;;
    esac
}

confirm() {
    msg="$1"
    if [ "$YES" -eq 1 ]; then
        return 0
    fi
    if [ -t 0 ]; then
        printf '%s [y/N] ' "$msg"
        read -r reply || reply=""
    elif [ -r /dev/tty ]; then
        printf '%s [y/N] ' "$msg" >&2
        read -r reply < /dev/tty || reply=""
    else
        err "No TTY available for prompt: \"$msg\". Re-run with --yes to proceed non-interactively."
    fi
    case "$reply" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

detect_uv() {
    if command -v uv >/dev/null 2>&1; then
        return 0
    fi
    confirm "uv is not installed. Install from https://astral.sh/uv?" \
        || err "uv is required; aborting."
    printf '+ curl -LsSf https://astral.sh/uv/install.sh | sh -s -- -q\n' >&2
    # Set the banner flag before any side effects, so the dry-run preview also
    # shows what a real run would print at the end.
    UV_INSTALLED_THIS_RUN=1
    if [ "$DRY_RUN" -eq 0 ]; then
        curl -LsSf https://astral.sh/uv/install.sh | sh -s -- -q
        if [ -d "$HOME/.local/bin" ]; then
            PATH="$HOME/.local/bin:$PATH"
            export PATH
        fi
        if ! command -v uv >/dev/null 2>&1; then
            err "uv install ran but 'uv' is not on PATH. Open a new shell and re-run install.sh."
        fi
    fi
}

pick_system_python() {
    # On macOS, prefer a system/Homebrew python3 over uv-managed
    # python-build-standalone (PBS). PBS binaries lack the entitlements that
    # `Security.framework` requires for keychain writes, so `pipefy auth login`
    # later fails with `(-25244, 'Unknown Error')` (errSecMissingEntitlement).
    # On Linux, uv's default Python is fine.
    [ "$OS" = "Darwin" ] || return 0
    # Honor UV_PYTHON only when it points at an absolute path (a user-pinned
    # interpreter). A version spec like `UV_PYTHON=3.13` leaves uv free to
    # resolve to PBS, which is the failure case this function exists to avoid.
    uv_python_is_spec=0
    case "${UV_PYTHON:-}" in
        /*) return 0 ;;
        ?*) uv_python_is_spec=1 ;;
    esac

    # Build a probe-local PATH that includes Homebrew's standard prefixes. A
    # `curl | sh` run from a non-interactive shell (CI, cron, freshly-spawned
    # subshell whose rc hasn't loaded Homebrew's shellenv) can inherit a PATH
    # of just /usr/bin and friends; without this, brew's python3 is invisible
    # and the loop falls through to PBS. The augmented PATH is scoped to the
    # probe so the rest of main() (uv, curl, python3, npx, pipefy lookups)
    # sees the unmodified PATH.
    # /usr/local/bin first, then /opt/homebrew/bin, so the Apple-Silicon-native
    # prefix lands at the front; on Intel /opt/homebrew/bin typically doesn't
    # exist and is skipped.
    probe_path="$PATH"
    for brew_dir in /usr/local/bin /opt/homebrew/bin; do
        [ -d "$brew_dir" ] && probe_path="$brew_dir:$probe_path"
    done

    keychain_hint="if 'pipefy auth login' later fails with keychain error -25244, set PIPEFY_KEYCHAIN_BACKEND=file or install Homebrew python3."

    for cmd in python3.14 python3.13 python3.12 python3.11 python3; do
        path=$(PATH="$probe_path"; command -v "$cmd" 2>/dev/null) || continue
        [ -n "$path" ] || continue
        # Probe version and resolve sys.executable in the same Python call so
        # the PBS-path filter runs against the real interpreter, not a symlink:
        # uv shims under ~/.local/bin/python3.NN point into PBS but their own
        # paths don't contain `/share/uv/python/`.
        real_path=$("$path" -c 'import os, sys; sys.version_info >= (3, 11) or sys.exit(1); print(os.path.realpath(sys.executable))' 2>/dev/null) || continue
        case "$real_path" in
            */.local/share/uv/python/*|*/share/uv/python/*) continue ;;
        esac
        PYTHON_OVERRIDE="$path"
        say "Using system Python for tool venvs: $path"
        say "  (avoids macOS keychain entitlement failures with uv-managed Python.)"
        if [ "$uv_python_is_spec" -eq 1 ]; then
            warn "UV_PYTHON=$UV_PYTHON (a version spec) overridden by $path to avoid PBS."
        fi
        return 0
    done

    if [ "$uv_python_is_spec" -eq 1 ]; then
        warn "UV_PYTHON=$UV_PYTHON is a version spec, not an absolute path, and no system python3 >= 3.11 was found on PATH. uv will resolve UV_PYTHON to its managed Python (PBS); $keychain_hint"
        return 0
    fi
    warn "No system python3 >= 3.11 found on PATH. uv will use its managed Python; $keychain_hint"
}

resolve_release() {
    if [ -n "$TAG" ]; then
        say "Using --version: $TAG"
        api_url="https://api.github.com/repos/$REPO/releases/tags/$TAG"
    else
        say "Resolving latest release from GitHub..."
        api_url="https://api.github.com/repos/$REPO/releases?per_page=1"
    fi
    body=$(curl -fsSL "$api_url") || err "Failed to reach GitHub API: $api_url"
    if [ -z "$TAG" ]; then
        TAG=$(printf '%s' "$body" \
            | grep -m1 '"tag_name"' \
            | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')
        [ -n "$TAG" ] || err "GitHub returned no releases for $REPO"
        say "Resolved tag: $TAG"
    fi
    WHEEL_URLS=$(printf '%s' "$body" \
        | grep '"browser_download_url"' \
        | grep -oE 'https://[^"]+\.whl' \
        || true)
    [ -n "$WHEEL_URLS" ] || err "Release $TAG has no wheel assets at $api_url"
    say "Wheels in $TAG:"
    printf '%s\n' "$WHEEL_URLS" | sed 's/^/  /'
}

install_tool() {
    pkg="$1"
    main_url=""
    set --
    while IFS= read -r url; do
        [ -z "$url" ] && continue
        # Skip sibling tools (each tool is installed in its own venv; bundling them
        # as --with would inject the sibling's binary into this tool's environment).
        skip=0
        for tool in $TOOLS; do
            [ "$tool" = "$pkg" ] && continue
            case "$url" in
                */"$tool"-*) skip=1; break ;;
            esac
        done
        if [ "$skip" -eq 1 ]; then
            continue
        fi
        case "$url" in
            */"$pkg"-*) main_url="$url" ;;
            *) set -- "$@" --with "$url" ;;
        esac
    done <<EOF
$WHEEL_URLS
EOF
    if [ -z "$main_url" ]; then
        err "Release $TAG does not ship a $pkg wheel"
    fi
    set -- "$@" "$main_url"
    say "Installing $pkg (this may take a few seconds)..."
    if [ -n "$PYTHON_OVERRIDE" ]; then
        run_quiet uv tool install --force --python "$PYTHON_OVERRIDE" "$@"
    else
        run_quiet uv tool install --force "$@"
    fi
}

install_skills() {
    if [ "$NO_SKILLS" -eq 1 ]; then
        return 0
    fi
    if ! command -v npx >/dev/null 2>&1; then
        warn "npx not found; skipping skills install. Install Node.js >= 18 or pass --no-skills to silence this warning."
        return 0
    fi
    if confirm "Install Pipefy skills via 'npx skills add'?"; then
        run npx skills add "$REPO" -y
    fi
}

claude_desktop_config_path() {
    printf '%s\n' "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
}

require_python3() {
    if ! command -v python3 >/dev/null 2>&1; then
        err "python3 is required for JSON config merge but was not found. Install python3 or use --client none."
    fi
}

require_claude() {
    if ! command -v claude >/dev/null 2>&1; then
        err "the 'claude' CLI is required to register the MCP server in Claude Code, but was not found. Install Claude Code (https://claude.com/claude-code), or re-run with --client none and paste the snippet manually."
    fi
}

claude_code_register_pipefy() {
    # Register at USER scope: Claude Code resolves same-named servers
    # local > project > user > plugin, so a user-scope `pipefy` shadows the
    # plugin's bundled entry and only the binary installed above spawns. The
    # bare binary (not a uvx command) keeps the server on the system Python it
    # was installed with, without baking an interpreter path into user config.
    if [ "$DRY_RUN" -eq 0 ]; then
        require_claude
        # `claude mcp add` errors on a duplicate name; drop any prior user-scope
        # entry first to keep re-runs idempotent.
        claude mcp remove pipefy --scope user >/dev/null 2>&1 || true
    fi
    run claude mcp add pipefy --scope user -- pipefy-mcp-server
    [ "$DRY_RUN" -eq 1 ] || say "Registered 'pipefy' at user scope (overrides the plugin's bundled server)."
}

json_merge_pipefy() {
    path="$1"
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '+ ensure mcpServers.pipefy in %s (preserve existing entry if present)\n' "$path" >&2
        return 0
    fi
    require_python3
    mkdir -p "$(dirname "$path")"
    python3 - "$path" <<'PY'
import json, os, pathlib, sys, tempfile

p = pathlib.Path(sys.argv[1])
data = {}
if p.exists():
    text = p.read_text(encoding="utf-8").strip()
    if text:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            sys.stderr.write(
                f"error: {p} is not valid JSON ({exc}); "
                f"use --client none and paste the snippet manually\n"
            )
            sys.exit(1)
if not isinstance(data, dict):
    sys.stderr.write(
        f"error: {p} root is not a JSON object; "
        f"use --client none and paste the snippet manually\n"
    )
    sys.exit(1)
servers = data.get("mcpServers")
if not isinstance(servers, dict):
    servers = {}
    data["mcpServers"] = servers
if "pipefy" in servers:
    print(f"{p}: mcpServers.pipefy already present; leaving as-is")
    sys.exit(0)
servers["pipefy"] = {"command": "pipefy-mcp-server"}
fd, tmp_path = tempfile.mkstemp(prefix=p.name + ".", dir=str(p.parent))
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp_path, p)
except BaseException:
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    raise
print(f"Updated {p}")
PY
}

codex_append_pipefy() {
    path="$1"
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '+ append [mcp_servers.pipefy] section to %s (if not already present)\n' "$path" >&2
        return 0
    fi
    mkdir -p "$(dirname "$path")"
    if [ -f "$path" ] && grep -q '^\[mcp_servers\.pipefy\]' "$path"; then
        say "$path already has [mcp_servers.pipefy]; leaving as-is."
        return 0
    fi
    if [ -f "$path" ] && [ -s "$path" ]; then
        printf '\n' >> "$path"
    fi
    cat >> "$path" <<'TOML'
[mcp_servers.pipefy]
command = "pipefy-mcp-server"
TOML
    say "Updated $path"
}

print_manual_snippet() {
    cat <<'EOF'
Paste this into your MCP client's config (add to the existing `mcpServers` object):

{
  "mcpServers": {
    "pipefy": {
      "command": "pipefy-mcp-server"
    }
  }
}
EOF
}

write_client_config() {
    # cursor/claude-desktop/codex write the client's own config file; claude-code
    # instead registers via `claude mcp add` (user scope) to override the plugin.
    case "$CLIENT" in
        cursor)
            json_merge_pipefy "$HOME/.cursor/mcp.json"
            ;;
        claude-desktop)
            json_merge_pipefy "$(claude_desktop_config_path)"
            ;;
        codex)
            codex_append_pipefy "$HOME/.codex/config.toml"
            ;;
        claude-code)
            claude_code_register_pipefy
            ;;
        ""|none)
            print_manual_snippet
            ;;
        *)
            err "Unknown --client value: $CLIENT"
            ;;
    esac
}

print_next_steps() {
    say ""
    say "Install complete."
    if [ "$DRY_RUN" -eq 0 ] && command -v pipefy >/dev/null 2>&1; then
        pipefy --version || true
    fi
    if [ "$UV_INSTALLED_THIS_RUN" -eq 1 ]; then
        say ""
        say "==> uv was installed during this run."
        say "    'pipefy' and 'pipefy-mcp-server' live in \$HOME/.local/bin, which may"
        say "    not be on this shell's PATH yet. To add it for the CURRENT shell,"
        say "    either restart your shell or run:"
        say ""
        say "        source \$HOME/.local/bin/env       (sh, bash, zsh)"
        say "        source \$HOME/.local/bin/env.fish  (fish)"
        say ""
        say "    For future shells, uv typically updates your shell rc (~/.bashrc,"
        say "    ~/.zshrc, ~/.config/fish/conf.d/uv.fish). If a new terminal still"
        say "    can't find 'pipefy', add \$HOME/.local/bin to PATH manually."
    fi
    if [ "$CLIENT" = "claude-code" ]; then
        say ""
        say "==> Pipefy MCP server registered at user scope (overrides the plugin's"
        say "    bundled server). Reload or restart Claude Code for it to take effect."
        say "    For skills and slash commands, also install the plugin:"
        say "        /plugin marketplace add $REPO && /plugin install pipefy@pipefy"
    fi
    say ""
    say "Next: authenticate with Pipefy."
    say "  Default (browser):   pipefy auth login"
    say "  Headless (device):   pipefy auth login --device"
    if [ "$CLIENT" = "claude-code" ]; then
        say "  Via Claude Code:     /pipefy:login"
    fi
}

main() {
    parse_args "$@"
    refuse_root
    detect_platform
    case "$CLIENT:$OS" in
        claude-desktop:Linux)
            err "Claude Desktop has no Linux build. Use --client claude-code, --client cursor, or --client none (prints the snippet to paste into your own config)." ;;
    esac
    if [ -n "$PREFIX" ]; then
        UV_TOOL_DIR="$PREFIX"
        export UV_TOOL_DIR
    fi
    detect_uv
    pick_system_python
    resolve_release
    install_tool pipefy_cli
    install_tool pipefy_mcp_server
    install_skills
    write_client_config
    print_next_steps
}

main "$@"
