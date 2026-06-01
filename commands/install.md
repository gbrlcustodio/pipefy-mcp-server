---
name: install
description: Install the Pipefy CLI (pipefy-auth + pipefy-cli + pipefy-infra + pipefy-sdk) as a persistent uv tool.
disable-model-invocation: true
---

If `command -v pipefy` succeeds, surface `pipefy --version` and stop.

Otherwise prompt the user to confirm running:

```
curl -fsSL https://raw.githubusercontent.com/gbrlcustodio/pipefy-mcp-server/main/install.sh \
  | sh -s -- --yes --no-skills --client none
```

The installer resolves the latest GitHub Release at runtime and runs `uv tool install` with the discovered wheel URLs. `--client none` skips MCP-client config writes; the Claude Code plugin's `.mcp.json` already wires the MCP server.

Verify with `pipefy --version`.
