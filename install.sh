#!/bin/sh
# install.sh — one-command installer for Pipefy CLI + MCP server.
#
# Resolves the latest GitHub Release tag (or a tag passed via --version),
# discovers its wheel assets, installs the CLI and MCP server via
# `uv tool install`, optionally installs skills via `npx skills add`, and
# writes the MCP server registration into the chosen client's config.

set -eu

REPO="gbrlcustodio/pipefy-mcp-server"

YES=0
NO_SKILLS=0
CLIENT=""
TAG=""
PREFIX=""
ALLOW_ROOT=0
DRY_RUN=0

OS=""
WHEEL_URLS=""

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

print_help() {
    cat <<EOF
Usage: install.sh [OPTIONS]

Install the Pipefy CLI and MCP server via uv, optionally add skills,
and register the MCP server with an MCP client.

Options:
  --yes, -y           Skip all confirmation prompts.
  --no-skills         Skip the skills installation step.
  --client <id>       Register MCP server in this client's config.
                      One of: claude-code, claude-desktop, cursor, codex, none.
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
    printf '+ curl -LsSf https://astral.sh/uv/install.sh | sh\n' >&2
    if [ "$DRY_RUN" -eq 0 ]; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        if [ -d "$HOME/.local/bin" ]; then
            PATH="$HOME/.local/bin:$PATH"
            export PATH
        fi
        if ! command -v uv >/dev/null 2>&1; then
            err "uv install ran but 'uv' is not on PATH. Open a new shell and re-run install.sh."
        fi
    fi
}

resolve_tag() {
    if [ -n "$TAG" ]; then
        say "Using --version: $TAG"
        return 0
    fi
    say "Resolving latest release tag from GitHub..."
    TAG="$(curl -fsSL "https://api.github.com/repos/$REPO/releases" \
        | grep -m1 '"tag_name"' \
        | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')"
    if [ -z "$TAG" ]; then
        err "Could not resolve latest release tag from https://api.github.com/repos/$REPO/releases"
    fi
    say "Resolved tag: $TAG"
}

fetch_release_assets() {
    WHEEL_URLS="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/tags/$TAG" \
        | grep '"browser_download_url"' \
        | grep -oE 'https://[^"]+\.whl' \
        || true)"
    if [ -z "$WHEEL_URLS" ]; then
        err "No wheel assets in release $TAG"
    fi
    say "Wheels in $TAG:"
    # WHEEL_URLS is newline-separated; iterate via while-read to avoid IFS surprises.
    printf '%s\n' "$WHEEL_URLS" | while IFS= read -r url; do
        [ -z "$url" ] && continue
        printf '  %s\n' "$url"
    done
}

install_tool() {
    pkg="$1"
    main_url=""
    set --
    while IFS= read -r url; do
        [ -z "$url" ] && continue
        case "$url" in
            */"$pkg"-*)
                main_url="$url"
                ;;
            *)
                set -- "$@" --with "$url"
                ;;
        esac
    done <<EOF
$WHEEL_URLS
EOF
    if [ -z "$main_url" ]; then
        err "Release $TAG does not ship a $pkg wheel"
    fi
    set -- "$@" "$main_url"
    run uv tool install --force "$@"
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
    case "$OS" in
        Darwin) printf '%s\n' "$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
        Linux)  printf '%s\n' "$HOME/.config/Claude/claude_desktop_config.json" ;;
        *)      err "Unsupported OS for --client claude-desktop: $OS" ;;
    esac
}

require_python3() {
    if ! command -v python3 >/dev/null 2>&1; then
        err "python3 is required for JSON config merge but was not found. Install python3 or use --client none."
    fi
}

json_merge_pipefy() {
    path="$1"
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '+ merge {"mcpServers": {"pipefy": {"command": "pipefy-mcp-server"}}} into %s\n' "$path" >&2
        return 0
    fi
    require_python3
    mkdir -p "$(dirname "$path")"
    python3 - "$path" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
data = {}
if p.exists():
    text = p.read_text(encoding="utf-8").strip()
    if text:
        data = json.loads(text)
data.setdefault("mcpServers", {})["pipefy"] = {"command": "pipefy-mcp-server"}
p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
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
    case "$CLIENT" in
        cursor)
            target="$HOME/.cursor/mcp.json"
            json_merge_pipefy "$target"
            say "Updated $target"
            ;;
        claude-desktop)
            target="$(claude_desktop_config_path)"
            json_merge_pipefy "$target"
            say "Updated $target"
            ;;
        codex)
            target="$HOME/.codex/config.toml"
            codex_append_pipefy "$target"
            say "Updated $target"
            ;;
        claude-code)
            cat <<EOF
To install in Claude Code, run these slash commands:
  /plugin marketplace add $REPO
  /plugin install pipefy@pipefy
EOF
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
    say ""
    say "Next: authenticate with Pipefy."
    say "  Default (browser):   pipefy auth login"
    say "  Headless (device):   pipefy auth login --device"
    if [ "$CLIENT" = "claude-code" ]; then
        say "  Via Claude Code:     /pipefy-login"
    fi
}

main() {
    parse_args "$@"
    refuse_root
    detect_platform
    if [ -n "$PREFIX" ]; then
        UV_TOOL_DIR="$PREFIX"
        export UV_TOOL_DIR
    fi
    detect_uv
    resolve_tag
    fetch_release_assets
    install_tool pipefy_cli
    install_tool pipefy_mcp_server
    install_skills
    write_client_config
    print_next_steps
}

main "$@"
