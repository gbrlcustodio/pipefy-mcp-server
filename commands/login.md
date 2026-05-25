---
name: login
description: Authenticate with Pipefy via OAuth (browser login). Stores the session in the OS keychain so the Pipefy MCP server's stored-session tier can use it. Installs the Pipefy CLI persistently if it isn't already on PATH so subsequent auth-status / refresh commands have a stable binary to run against.
disable-model-invocation: true
argument-hint: "[--no-browser] [--callback-timeout <seconds>]"
---

First, check whether the Pipefy CLI is installed:

```
command -v pipefy
```

If `pipefy` is **not** on PATH, install it before attempting login so the user has a stable binary for subsequent `pipefy auth status` / `pipefy auth logout` invocations. Run the following command and prompt the user to confirm:

```
uv tool install --force \
  --with "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/sdk" \
  --with "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/auth" \
  "git+https://github.com/gbrlcustodio/pipefy-mcp-server@dev#subdirectory=packages/cli"
```

`--with` is required because each workspace member's `[tool.uv.sources]` declares its siblings as `{ workspace = true }`, which uv cannot resolve from a remote git URL — issue #234 tracks switching to release-wheel URLs once they ship all four packages.

## macOS first-run keychain ACL (one-time, per user)

`uv tool install` provisions its own standalone CPython under `~/.local/share/uv/python/...`. macOS Keychain ACL is per-calling-binary; that interpreter has no ACL entry on the `pipefy` keychain service yet. The OAuth handshake will succeed but the keychain write fails with `errSecParam (-25244)` because the macOS "Allow access" prompt cannot render in this non-TTY subprocess context.

**If `pipefy auth login` has never been run on this machine from a regular Terminal.app session**, instruct the user to run it manually **outside** Claude Code:

```
PIPEFY_AUTH_URL=<your OIDC issuer URL> pipefy auth login
```

When macOS shows the keychain-access dialog, click **Always Allow**. After that the ACL persists and subsequent `/pipefy:login` invocations from this session work without prompting. Re-run this slash command after the user confirms the first manual login succeeded.

Issue #235 tracks platform-aware error messaging so the CLI can surface this exact guidance inline.

## Run the login

Then run, prompting the user to confirm:

```
pipefy auth login $ARGUMENTS
```

`PIPEFY_AUTH_URL` must be set in the shell environment where this runs — the OIDC issuer URL, e.g. `https://signin.pipefy.com/realms/pipefy`. The shell env of the Claude Code session is what `pipefy auth login` inherits; configuring the MCP server's env via `.mcp.json` does not feed this subprocess. Issue #233 will make `PIPEFY_AUTH_URL` an optional override by baking a CLI-level default to the Pipefy prod IdP.

On success the OAuth session is written to the OS keychain. A live MCP server picks up the rotated session on its next tool call; if the server failed to start because credentials were missing, restart it (or restart Claude Code) after login completes.

Pass `--no-browser` to print the authorization URL instead of opening a browser, and `--callback-timeout <seconds>` to override the default 180-second loopback wait.
