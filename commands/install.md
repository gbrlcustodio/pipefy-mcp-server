---
name: install
description: Install the Pipefy CLI (pipefy-cli + pipefy-auth + pipefy-sdk) as a persistent uv tool. Required before /pipefy:login can store the OAuth session in the OS keychain (uvx's ephemeral binary identity is rejected by macOS Keychain).
disable-model-invocation: true
---

Run the following command. The user must confirm before it executes — do not pre-approve.

```
uv tool install --force \
  --with "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server#subdirectory=packages/sdk" \
  --with "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server#subdirectory=packages/auth" \
  "git+https://github.com/gbrlcustodio/pipefy-mcp-server#subdirectory=packages/cli"
```

After install, `pipefy` is on PATH. Verify with `pipefy --version`.

The `--with` chain is required today because each workspace member's `[tool.uv.sources]` declares its siblings as `{ workspace = true }`, which uv cannot resolve from a remote git URL — only from a local workspace context. Issue #234 tracks switching this to release-wheel URLs once the next tag ships all four wheels (SDK + CLI + MCP + Auth).
