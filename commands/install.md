---
name: install
description: Install the Pipefy CLI (pipefy-cli + pipefy-auth + pipefy) as a persistent uv tool.
disable-model-invocation: true
---

If `command -v pipefy` succeeds, surface `pipefy --version` and stop.

Otherwise prompt the user to confirm running:

```
uv tool install --force \
  --with "pipefy @ git+https://github.com/pipefy/ai-toolkit@latest#subdirectory=packages/sdk" \
  --with "pipefy-auth @ git+https://github.com/pipefy/ai-toolkit@latest#subdirectory=packages/auth" \
  "git+https://github.com/pipefy/ai-toolkit@latest#subdirectory=packages/cli"
```

Verify with `pipefy --version`.
