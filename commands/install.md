---
name: install
description: Install the Pipefy CLI (pipefy-cli + pipefy-auth + pipefy-sdk) as a persistent uv tool.
disable-model-invocation: true
---

If `command -v pipefy` succeeds, surface `pipefy --version` and stop.

Otherwise prompt the user to confirm running:

```
uv tool install --force \
  --with "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/sdk" \
  --with "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/auth" \
  "git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/cli"
```

Verify with `pipefy --version`.
