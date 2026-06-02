#!/bin/sh
# SessionStart nudge: when install.sh has registered a user-scope `pipefy`
# server (the persistent pipefy-mcp-server binary, which shadows the plugin's
# bundled uvx entry), plugin auto-updates no longer reach that running server.
# This compares the installed binary's version against the plugin's declared
# version and, on drift, asks the user to re-run /pipefy:install.
#
# No-op for users on the pure plugin/uvx path: they have no installed binary,
# so there is nothing shadowing the plugin and nothing to update.
set -eu

# No installed binary means nothing shadows the plugin, so there is no
# user-scope override that could drift -> nothing to nudge about.
command -v pipefy-mcp-server >/dev/null 2>&1 || exit 0

# Cheap checks first; only spawn the binary (Python cold start) once we have a
# plugin version to compare against.
manifest="${CLAUDE_PLUGIN_ROOT:-}/.claude-plugin/plugin.json"
[ -f "$manifest" ] || exit 0
plugin=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$manifest" | head -n1)
[ -n "$plugin" ] || exit 0

installed=$(pipefy-mcp-server --version 2>/dev/null | tr -d '[:space:]') || exit 0
[ -n "$installed" ] || exit 0

if [ "$installed" != "$plugin" ]; then
    echo "Pipefy: the installed MCP server ($installed) differs from this plugin ($plugin); re-run /pipefy:install to sync."
fi
exit 0
