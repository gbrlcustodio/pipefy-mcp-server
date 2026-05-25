---
name: login
description: Authenticate with Pipefy via OAuth (browser login). Stores the session in the OS keychain so the Pipefy MCP server's stored-session tier can use it. Installs the Pipefy CLI persistently if it isn't already on PATH (uvx ephemeral binaries are rejected by the macOS Keychain).
disable-model-invocation: true
argument-hint: "[--no-browser] [--callback-timeout <seconds>]"
---

First, check whether the Pipefy CLI is installed:

```
command -v pipefy
```

If `pipefy` is **not** on PATH, install it persistently before attempting login. Run the following command and prompt the user to confirm:

```
uv tool install --force \
  --with "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/sdk" \
  --with "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/auth" \
  "git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/cli"
```

`uvx --from`-based one-shot invocations cannot store the OAuth session in the macOS Keychain because the ephemeral Python binary lacks a stable identity that macOS Keychain accepts for new-item writes. A persistent `uv tool install` is required. `--with` is required because each workspace member's `[tool.uv.sources]` declares its siblings as `{ workspace = true }`, which uv cannot resolve from a remote git URL — issue #234 tracks switching to release-wheel URLs once they ship all four packages.

Then run, prompting the user to confirm:

```
pipefy auth login $ARGUMENTS
```

`PIPEFY_AUTH_URL` must be set in the shell environment where this runs — the OIDC issuer URL, e.g. `https://signin.pipefy.com/realms/pipefy`. The shell env of the Claude Code session is what `pipefy auth login` inherits; configuring the MCP server's env via `.mcp.json` does not feed this subprocess. Issue #233 will make `PIPEFY_AUTH_URL` an optional override by baking a CLI-level default to the Pipefy prod IdP.

On success the OAuth session is written to the OS keychain. A live MCP server picks up the rotated session on its next tool call; if the server failed to start because credentials were missing, restart it (or restart Claude Code) after login completes.

Pass `--no-browser` to print the authorization URL instead of opening a browser, and `--callback-timeout <seconds>` to override the default 180-second loopback wait.
