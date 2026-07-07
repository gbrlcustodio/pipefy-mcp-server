---
name: install
description: Install the Pipefy CLI (pipefy-cli + pipefy-auth + pipefy) as a persistent uv tool.
disable-model-invocation: true
---

If `command -v pipefy` succeeds, surface `pipefy --version` and stop.

Otherwise prompt the user to confirm running:

```
uv tool install --force pipefy-cli
```

Verify with `pipefy --version`.
