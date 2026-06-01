---
name: install
description: Install the Pipefy CLI (pipefy-auth + pipefy-cli + pipefy-infra + pipefy-sdk) as a persistent uv tool.
disable-model-invocation: true
---

If `command -v pipefy` succeeds, surface `pipefy --version` and stop.

Otherwise prompt the user to confirm running:

```
uv tool install --force \
  --with https://github.com/gbrlcustodio/pipefy-mcp-server/releases/download/v0.2.0-beta.2/pipefy_sdk-0.2.0b2-py3-none-any.whl \
  --with https://github.com/gbrlcustodio/pipefy-mcp-server/releases/download/v0.2.0-beta.2/pipefy_auth-0.2.0b2-py3-none-any.whl \
  --with https://github.com/gbrlcustodio/pipefy-mcp-server/releases/download/v0.2.0-beta.2/pipefy_infra-0.2.0b2-py3-none-any.whl \
  https://github.com/gbrlcustodio/pipefy-mcp-server/releases/download/v0.2.0-beta.2/pipefy_cli-0.2.0b2-py3-none-any.whl
```

Verify with `pipefy --version`.
