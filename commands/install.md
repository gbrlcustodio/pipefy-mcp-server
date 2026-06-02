---
name: install
description: Install the Pipefy CLI and MCP server as persistent uv tools, and register the server in Claude Code at user scope.
disable-model-invocation: true
---

If `command -v pipefy` succeeds, surface `pipefy --version` and stop.

Otherwise prompt the user to confirm running:

```
curl -fsSL https://raw.githubusercontent.com/pipefy/ai-toolkit/main/install.sh \
  | sh -s -- --yes --no-skills --client claude-code
```

The installer resolves the latest GitHub Release at runtime and runs `uv tool install` with the discovered wheel URLs. `--client claude-code` registers the MCP server via `claude mcp add` at user scope, which takes precedence over the plugin's bundled `.mcp.json` entry so the system-Python binary is the one that runs. Reload or restart Claude Code afterward for the registration to take effect.

Verify with `pipefy --version`.
