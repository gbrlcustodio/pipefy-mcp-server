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

## Run the login

Run, prompting the user to confirm:

```
pipefy auth login $ARGUMENTS
```

`PIPEFY_AUTH_URL` must be set in the shell environment where this runs — the OIDC issuer URL, e.g. `https://signin.pipefy.com/realms/pipefy`. The shell env of the Claude Code session is what `pipefy auth login` inherits; configuring the MCP server's env via `.mcp.json` does not feed this subprocess. Issue #233 will make `PIPEFY_AUTH_URL` an optional override by baking a CLI-level default to the Pipefy prod IdP.

On success the OAuth session is written to the OS keychain. A live MCP server picks up the rotated session on its next tool call; if the server failed to start because credentials were missing, restart it (or restart Claude Code) after login completes.

Pass `--no-browser` to print the authorization URL instead of opening a browser, and `--callback-timeout <seconds>` to override the default 180-second loopback wait.

## macOS keychain `errSecParam (-25244)` (intermittent)

On macOS, `pipefy auth login` may exit with `errSecParam (-25244)` at the final keychain-write step even though OAuth itself succeeded. The cause is not yet reliably diagnosed — direct `keyring.set_password` calls from the same uv-tool-installed Python succeed under repro testing, so this is likely a transient `Security.framework` condition rather than a per-binary ACL problem.

If this happens:

1. **Retry** the slash command. The transient condition usually clears on a second attempt.
2. If retry still fails, run `pipefy auth login` once from a regular Terminal.app session as a fallback. Approve any macOS keychain dialog that appears.

Issue #235 tracks platform-aware error messaging.
