#!/bin/sh
# SessionStart nudge: when install.sh has registered a user-scope `pipefy`
# server (the persistent pipefy-mcp-server binary, which shadows the plugin's
# bundled uvx entry), plugin auto-updates no longer reach that running server.
# This compares the installed binary's version against the plugin's declared
# version and, on drift, tells the user to re-run install.sh (the path that
# actually reinstalls the binary and re-registers the user-scope server;
# /pipefy:install only installs the CLI).
#
# No-op unless that user-scope override is registered: users on the pure
# plugin/uvx path have no installed binary, and users who installed the binary
# only for another client (e.g. --client cursor) still run the plugin's uvx
# server here, so there is nothing shadowing the plugin to nudge about.
set -eu

# Cheap pre-filter: no installed binary means nothing could shadow the plugin.
command -v pipefy-mcp-server >/dev/null 2>&1 || exit 0

# The precise trigger is a user-scope `pipefy` server whose command is that
# binary. `command -v` alone is not enough: --client cursor also puts the
# binary on PATH without registering a Claude Code override, so the plugin's
# uvx server still runs here and there is nothing to sync. Fall through to no
# nudge if python3 is missing or the config cannot be read.
python3 - <<'PY' || exit 0
import json
import os
import sys

try:
    servers = json.load(open(os.path.expanduser("~/.claude.json"))).get("mcpServers", {})
except (OSError, ValueError):
    sys.exit(1)
entry = servers.get("pipefy") if isinstance(servers, dict) else None
command = entry.get("command") if isinstance(entry, dict) else None
sys.exit(0 if command == "pipefy-mcp-server" else 1)
PY

# Cheap checks first; only spawn the binary (Python cold start) once we have a
# plugin version to compare against.
manifest="${CLAUDE_PLUGIN_ROOT:-}/.claude-plugin/plugin.json"
[ -f "$manifest" ] || exit 0
plugin=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$manifest" | head -n1)
[ -n "$plugin" ] || exit 0

installed=$(pipefy-mcp-server --version 2>/dev/null | tr -d '[:space:]')
[ -n "$installed" ] || exit 0

if [ "$installed" != "$plugin" ]; then
    echo "Pipefy: the installed MCP server ($installed) differs from this plugin ($plugin). Re-run the installer to sync: curl -fsSL https://raw.githubusercontent.com/pipefy/ai-toolkit/main/install.sh | sh -s -- --client claude-code"
fi
exit 0
