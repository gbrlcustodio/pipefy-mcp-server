---
name: install
description: Install the Pipefy CLI (pipefy-cli + pipefy-auth + pipefy-sdk) as a persistent uv tool so `/pipefy:login` and subsequent `pipefy auth status` / `pipefy auth logout` invocations have a stable binary on PATH.
disable-model-invocation: true
---

First, check whether `pipefy` is already on PATH:

```
command -v pipefy
```

If it is, surface `pipefy --version` and stop — there is no reason to reinstall.

Otherwise run the following command. The user must confirm before it executes — do not pre-approve.

```
uv tool install --force \
  --with "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/sdk" \
  --with "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/auth" \
  "git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/cli"
```

After install, `pipefy` is on PATH. Verify with `pipefy --version`.

The `--with` chain is required today because each workspace member's `[tool.uv.sources]` declares its siblings as `{ workspace = true }`, which uv cannot resolve from a remote git URL — only from a local workspace context. Issue #234 tracks switching this to release-wheel URLs once the next tag ships all four wheels (SDK + CLI + MCP + Auth).

## macOS post-install: prime keychain ACL (one-time)

`uv tool install` provisions its own standalone CPython under `~/.local/share/uv/python/...`. macOS Keychain ACL is per-calling-binary; that interpreter has no ACL entry on the `pipefy` keychain service yet. Until granted, `pipefy auth login` will fail at the keychain write with `errSecParam (-25244)` because the macOS "Allow access" dialog cannot render in a non-TTY subprocess.

Instruct the user to run `pipefy auth login` **once manually from their own Terminal.app session** (outside Claude Code) and click **Always Allow** when the macOS keychain dialog appears:

```
PIPEFY_AUTH_URL=<your OIDC issuer URL> pipefy auth login
```

After that the ACL persists and `/pipefy:login` from Claude Code works without prompting. Issue #235 tracks surfacing this guidance from inside the CLI's keychain-failure error path.
