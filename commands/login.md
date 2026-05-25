---
name: login
description: Authenticate with Pipefy via OAuth (browser login). Stores the session in the OS keychain so the Pipefy MCP server's stored-session tier can use it. Requires the Pipefy CLI to be installed (see /pipefy:install).
disable-model-invocation: true
argument-hint: "[--no-browser] [--callback-timeout <seconds>]"
---

First, check whether the Pipefy CLI is installed:

```
command -v pipefy
```

If `pipefy` is **not** on PATH, invoke the `/pipefy:install` slash command first (or run its install command inline). Do not proceed to the login step until `pipefy` is available — `uvx --from`-based one-shot invocations cannot store the OAuth session in the macOS Keychain because the ephemeral Python binary lacks a stable identity that macOS Keychain accepts for new-item writes.

Then run, prompting the user to confirm:

```
pipefy auth login $ARGUMENTS
```

On success the OAuth session is written to the OS keychain. A live MCP server picks up the rotated session on its next tool call; if the server failed to start because credentials were missing, restart it (or restart Claude Code) after login completes.

Pass `--no-browser` to print the authorization URL instead of opening a browser, and `--callback-timeout <seconds>` to override the default 180-second loopback wait.

`PIPEFY_AUTH_URL` must be set in the environment (the OIDC issuer URL, e.g. `https://signin.pipefy.com/realms/pipefy`). Issue #233 will make this an optional override by baking a CLI-level default to the Pipefy prod IdP.
